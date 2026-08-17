# Interview Evidence Platform Contracts

This package is the machine-readable foundation contract for all four implementation lanes.

- `openapi/root.yaml` composes the lane-owned REST path/schema fragments. It is deterministically
  split from the approved baseline in `specs/001-interview-evidence-platform/contracts/openapi.yaml`.
- `events/websocket/v1/` contains the protocol envelope, every client/server message schema, and a
  valid example for each message type.
- `events/catalog.v1.json` indexes all v1 asynchronous domain events, their owners/consumers,
  schemas, and sanitized examples. The shared envelope is `events/common/v1/envelope.json`.
- `modules/v1/` contains tenant-scoped snapshots for every public cross-module read boundary.
- `generated/` contains deterministic Python, TypeScript, and bundled JSON Schema outputs.

Run the generator to update derived files, then use check mode in CI:

```text
python packages/contracts/scripts/generate_contracts.py
python packages/contracts/scripts/generate_contracts.py --check
```

Do not hand-edit `openapi/` or `generated/`; both are generator-owned. WebSocket, async-event, and
module-snapshot JSON Schemas are canonical inputs and require the contract change protocol.

## Compatibility

Additive optional fields are backward compatible within v1. A required field, removed field or
value, renamed route/event/message, or changed meaning requires a new major contract version and
consumer migration. New enum values require consumers to support a safe unknown branch first.

All async schemas require `company_id`; applicant/source text, answer text, credentials, tokens,
and signed URLs are prohibited from async payloads. WebSocket protected payloads may contain live
question/transcript text, but those values must never enter operational logs.
