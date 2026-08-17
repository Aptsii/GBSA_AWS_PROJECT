# Generated Contract Bindings

These files are deterministic outputs of the canonical REST, WebSocket, asynchronous-event and
module-snapshot schemas in `packages/contracts`.

Do not edit files in this directory by hand. Run:

```text
python packages/contracts/scripts/generate_contracts.py
python packages/contracts/scripts/generate_contracts.py --check
```

The Python output uses standard-library `TypedDict`/`Literal` types. The TypeScript output uses
structural aliases, so consumers require no contract-generator runtime dependency.
