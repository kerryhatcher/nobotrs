# Integration acceptance

`scripts/integration_acceptance.py` exercises the real executable with synthetic
prose. It checks suppression before overlap selection, per-path and inline scopes,
audit/display invariance, Unicode SARIF locations and schema validity, advisory
hook status translation, the actual code-scanning example's shell, pre-commit's
multiple-file invocation, and the embedded guide. These checks establish adapter
behavior; they do not measure authorship accuracy. The pre-commit check exercises
the configured command contract, rather than installing the pre-commit host.
The workflow check executes its shell locally; it does not upload to GitHub.

Use the [OASIS SARIF 2.1.0 errata01 schema](https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/sarif-schema-2.1.0.json),
whose exact bytes must have SHA-256
`c3b4bb2d6093897483348925aaa73af03b3e3f4bd4ca38cef26dcb4212a2682e`.
Acquisition is an explicit development step; the executable does not download
schemas or require Python.

```sh
curl --fail --location 'https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/sarif-schema-2.1.0.json' -o /tmp/nobotrs-sarif-schema.json
cargo build --locked
uv run --with jsonschema==4.26.0 python scripts/integration_acceptance.py --schema /tmp/nobotrs-sarif-schema.json
```

The runner verifies the schema checksum before using it and uses a temporary
configuration directory with all inherited `NOBOTRS_*` settings removed. Hook
checks include the real binary and controlled subprocesses for all four statuses.
Corpus payloads and held-out evaluation data are never read by these checks.
