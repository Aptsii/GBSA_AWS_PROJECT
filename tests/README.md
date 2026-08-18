# Shared Test Roots

This directory contains cross-lane validation assets. Domain tests stay beside the owning backend
or frontend module; only the Integration owner changes shared fixtures and end-to-end composition.

| Path                    | Purpose                                                                        | Owner               |
| ----------------------- | ------------------------------------------------------------------------------ | ------------------- |
| `e2e/`                  | Merged thin journey, isolation, deletion, human-control, and stage smoke tests | Integration         |
| `fixtures/shared/`      | Deterministic identifiers and producer/consumer contract fixtures              | Integration         |
| `regression/retrieval/` | Korean document and public-code retrieval cases                                | Lane B              |
| `regression/questions/` | Safe-question, idempotency, and degraded-mode cases                            | Lane C              |
| `regression/evidence/`  | Evidence-state and unsupported-claim cases                                     | Lane D              |
| `load/`                 | Pilot concurrency and Evidence-seek measurements                               | Lane C or D by task |

Fixtures must use synthetic data and opaque identifiers. Do not store applicant source text,
answers, credentials, tokens, signed URLs, or real personal data here.

## Compose browser journey

```bash
make compose-up
make browser-install
make test-e2e-browser
```

The journey uses the local-only company principal and authenticated fixture route. The fixture
route is not mounted outside the `local` runtime environment.
