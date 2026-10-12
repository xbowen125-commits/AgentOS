# Spatial AI NPC Integration

AgentOS can act as the reasoning backend for a multimodal or spatial NPC without importing Unity,
camera, microphone, or computer-vision dependencies.

## Flow

```text
Vision / Speech / Unity
          |
          v
  Interaction Event
          |
          v
 InteractionAdapter
          |
          v
    AgentOS Runtime
          |
          v
    Planner -> LLM
          |
          v
      NPCAction
          |
          v
        Unity
```

## Perception protocol

Supported event types are `player.detected`, `player.wave`, `player.look`, and `player.speech`.
External systems send JSON-compatible structured data:

```json
{
  "type": "player.wave",
  "payload": {
    "confidence": 0.93
  }
}
```

`InteractionAdapter` converts this event into a public Agent input. It does not access sensors or
engine APIs.

## Action protocol

The adapter returns an `NPCAction`, which can be reduced to a minimal bridge message:

```json
{
  "type": "npc_action",
  "action": "wave",
  "text": "你好"
}
```

Transport is intentionally out of scope. A Unity project can carry this document over its chosen
HTTP, WebSocket, message-queue, or native bridge without changing AgentOS core.

## Structured player memory

`NPCMemory` persists only:

- player ID;
- interaction count;
- last action;
- bounded relationship level.

It does not persist faces, raw images, audio, voiceprints, or other biometric data. Perception
payloads are used for the current interaction and are not copied into the player profile.

## Events and correlation

The adapter emits `interaction.received`, `npc.action.generated`, and `memory.updated`. An
`interaction_id` correlates the external event with the Agent run ID while preserving the runtime's
existing trace model.
