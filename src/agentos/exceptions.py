"""AgentOS exception definitions."""


class AgentOSError(Exception):
    """Base exception for AgentOS errors."""


class ToolRuntimeError(AgentOSError):
    """Base exception for tool runtime errors."""


class ToolAlreadyRegisteredError(ToolRuntimeError):
    """Raised when a tool name is registered more than once."""


class ToolNotFoundError(ToolRuntimeError):
    """Raised when a requested tool is not registered."""


class ToolArgumentError(ToolRuntimeError):
    """Raised when a tool receives invalid arguments."""


class ToolExecutionError(ToolRuntimeError):
    """Raised when a tool fails during execution."""


class MemoryStoreError(AgentOSError):
    """Base exception for memory persistence errors."""


class MemoryFormatError(MemoryStoreError):
    """Raised when a memory document is not valid JSON or has an invalid shape."""


class MemoryVersionError(MemoryStoreError):
    """Raised when a memory document uses an unsupported schema version."""


class MemoryItemNotFoundError(MemoryStoreError):
    """Raised when a memory item cannot be found by ID."""


class PlannerError(AgentOSError):
    """Base exception for planner failures."""


class PlannerOutputError(PlannerError):
    """Raised when model output does not match the planner JSON protocol."""


class MiniLLMError(AgentOSError):
    """Base exception for the MiniLLM-Serve model adapter."""


class MiniLLMConnectionError(MiniLLMError):
    """Raised when MiniLLM-Serve cannot be reached or times out."""


class MiniLLMResponseError(MiniLLMError):
    """Raised when MiniLLM-Serve returns an invalid response."""


class TraceStoreError(AgentOSError):
    """Base exception for execution trace persistence errors."""


class TraceNotFoundError(TraceStoreError):
    """Raised when a requested execution trace does not exist."""


class TraceFormatError(TraceStoreError):
    """Raised when a trace document contains invalid JSON or data."""


class RuntimeControlError(AgentOSError):
    """Base exception for runtime execution controls."""


class RuntimeTimeoutError(RuntimeControlError):
    """Raised when a controlled asynchronous operation exceeds its timeout."""

