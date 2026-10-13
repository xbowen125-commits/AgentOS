"""Sandbox-only ablation assembly through the unchanged Planner protocol."""

import json
from collections.abc import Callable, Sequence
from copy import deepcopy
from functools import partial

from agentos.core.decision import FinalAnswerDecision, ToolCallDecision
from agentos.core.state import AgentState
from agentos.evaluation.ablation.result import AblationResult
from agentos.evaluation.ablation.variant import Variant
from agentos.evaluation.benchmark import BenchmarkRunner, TrialSession
from agentos.evaluation.task import EvaluationTask
from agentos.events import AgentEvent, EventBus
from agentos.exceptions import PlannerOutputError, RuntimeTimeoutError
from agentos.interfaces.model import Model
from agentos.planner.parser import parse_decision
from agentos.planner.planner import AgentDecision, Planner
from agentos.planner.prompt import build_planner_prompt
from agentos.planner.retry import PlannerRetryController
from agentos.planner.tool_prompt import ToolDescription
from agentos.planner.validator import DecisionValidator
from agentos.runtime.timeout import TimeoutController

AblationFactory = Callable[[Variant, EvaluationTask, int], TrialSession]


def _strict_decision(output: str) -> AgentDecision:
    """Minimum wire decoding without normalization or tool-semantic validation."""
    try:
        data = json.loads(output)
        if not isinstance(data, dict):
            raise TypeError("Decision must be an object")
        if data.get("type") == "tool_call":
            if not isinstance(data["tool_name"], str) or not isinstance(data["arguments"], dict):
                raise ValueError("Invalid tool decision shape")
            return ToolCallDecision(data["tool_name"], data["arguments"])
        if data.get("type") == "final" and isinstance(data["answer"], str):
            return FinalAnswerDecision(data["answer"])
        raise ValueError("Unknown decision type or answer shape")
    except (ValueError, KeyError, TypeError) as error:
        raise PlannerOutputError("Strict JSON decision decoding failed") from error


class AblationPlanner(Planner):
    """Experimental adapter, never a mutation of production ModelPlanner.

    Every variant uses the same prompt/tool descriptions. Only normalization,
    decision validation, output repair and planner timeout are switched here.
    Use only isolated synthetic tools when disabling planner protection.
    """

    def __init__(
        self, model: Model, variant: Variant, tools: Sequence[ToolDescription] = (),
        event_bus: EventBus | None = None,
    ) -> None:
        self.model = model
        self.variant = variant
        self.tools = deepcopy(tuple(tools))
        self.event_bus = event_bus

    async def _emit(self, event_type: str, state: AgentState) -> None:
        if self.event_bus is not None:
            try:
                await self.event_bus.emit(AgentEvent.create(
                    event_type, state.run_id, {"step": state.step_count + 1},
                ))
            except Exception:  # noqa: BLE001 -- observability remains side-channel
                return

    async def plan(self, state: AgentState) -> AgentDecision:
        async def decode(output: str) -> AgentDecision:
            try:
                decision = (parse_decision(output) if self.variant.parser_enabled
                            else _strict_decision(output))
            except PlannerOutputError:
                await self._emit("planner.parse.failed", state)
                raise
            if self.variant.validator_enabled:
                try:
                    return DecisionValidator(self.tools).validate(decision, state)
                except PlannerOutputError:
                    await self._emit("planner.validation.failed", state)
                    raise
            return decision

        async def generate() -> AgentDecision:
            # The existing retry controller accepts a synchronous decoder and
            # exposes repair events, not granular parse/validation stage events.
            controller = PlannerRetryController(
                self.variant.max_retries if self.variant.retry_enabled else 0, self.event_bus,
            )
            prompt = build_planner_prompt(state, self.tools)
            if not self.variant.retry_enabled:
                return await decode(await self.model.generate(prompt))

            def parse(output: str) -> AgentDecision:
                decision = (parse_decision(output) if self.variant.parser_enabled
                            else _strict_decision(output))
                return (DecisionValidator(self.tools).validate(decision, state)
                        if self.variant.validator_enabled else decision)

            return await controller.generate_decision(self.model, prompt, parse, state.run_id)

        try:
            if self.variant.timeout_enabled:
                return await TimeoutController(self.variant.timeout_seconds).run(generate())
            return await generate()
        except RuntimeTimeoutError:
            await self._emit("runtime.timeout", state)
            raise


class AblationRunner:
    """Compare isolated sessions built by a caller-supplied variant-aware factory.

    Factories must apply the variant (e.g. through AblationPlanner), create fresh
    model/state/tools/cache per trial, and subscribe session.events.append to the
    bus. Arbitrary external factory configuration cannot be verified automatically.
    """

    def __init__(self, benchmark: BenchmarkRunner | None = None) -> None:
        self.benchmark = benchmark or BenchmarkRunner()

    async def run(
        self, tasks: Sequence[EvaluationTask], variants: Sequence[Variant],
        factory: AblationFactory,
    ) -> AblationResult:
        variants = tuple(variants)
        if not variants or len({v.name for v in variants}) != len(variants):
            raise ValueError("Variants must be non-empty with unique names")
        frozen_tasks = deepcopy(tuple(tasks))
        results = {}
        for variant in variants:
            build = partial(factory, variant)
            results[variant.name] = await self.benchmark.run(frozen_tasks, build)
        return AblationResult(variants, results)
