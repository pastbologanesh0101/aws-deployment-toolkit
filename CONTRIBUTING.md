# Contributing

Thanks for considering a contribution to AWS Deployment Toolkit.

## Running the tests

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
pip install -r requirements-dev.txt   # adds moto + pytest

pytest tests/ -v
```

The whole suite runs offline via [`moto`](https://github.com/getmoto/moto)'s
`@mock_aws` decorator — no AWS credentials or network access are needed.
Tests exercise the toolkit's actual logic (hash comparison, create-vs-update
branching, status polling) against moto's mocked S3/Lambda/IAM/
CloudFormation, not against stubs of the toolkit itself, so new tests
should follow the same pattern: use real boto3 clients under `@mock_aws`
rather than mocking `S3Syncer`/`LambdaDeployer`/`CloudFormationDeployer`
methods directly.

## Code style

- Type hints on public functions/methods (see `s3_sync.py`,
  `lambda_deploy.py`), using `from __future__ import annotations` for
  `X | None`-style unions.
- Module and class docstrings that explain *why* a design choice was made
  (e.g. the ETag/MD5 comparison in `s3_sync.py`), not just what the code does.
- CLI errors should be reported via `click.echo(..., err=True)` followed by
  `sys.exit(1)`, matching the existing commands in `cli.py` — avoid letting
  raw tracebacks reach the user for expected failure cases (missing local
  paths, malformed `--param` values, etc).
- No new dependencies beyond `boto3`/`click` for the library, or
  `moto`/`pytest` for tests, unless there's no reasonable alternative.

## Submitting changes

1. Fork the repo and create a branch for your change.
2. Add or update tests under `tests/` for any behavior change — see above
   for the moto-based testing pattern.
3. Run `pytest tests/ -v` and make sure everything passes on the Python
   versions listed in `.github/workflows/tests.yml`.
4. Open a pull request describing the change and why it's needed.
