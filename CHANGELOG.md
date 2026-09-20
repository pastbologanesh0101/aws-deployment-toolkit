# Changelog

## [0.1.0] - Initial release

The initial release of AWS Deployment Toolkit: a focused CLI (`adt`) and
Python library for three real AWS deployment workflows, built on `boto3`.

Included:

- `s3_sync.py` — `S3Syncer`, an incremental directory-to-bucket sync that
  compares each local file's MD5 against the target object's S3 ETag (valid
  for single-part uploads) so only new/changed files are uploaded; ships a
  `--dry-run` mode and auto-creates the bucket if missing.
- `lambda_deploy.py` — `LambdaDeployer`, which zips a local source
  directory in memory and creates the Lambda function if it doesn't exist,
  or updates its code and configuration if it does.
- `cloudformation.py` — `CloudFormationDeployer`, deploying a bundled
  template (an S3 bucket + an SNS topic) with create-or-update logic
  (treating "No updates are to be performed" as a successful no-op), plus
  `wait_for_completion()` to poll `StackStatus` to a terminal state.
- `cli.py` — a `click`-based CLI (`adt s3-sync`, `adt lambda-deploy`,
  `adt cfn-deploy`, `adt cfn-status`) wrapping all three workflows, with a
  built-in `--version` flag.
- A test suite (`tests/`) covering S3 sync (new/changed/unchanged files,
  dry-run, bucket auto-creation, missing-directory errors), Lambda deploy
  (create and update paths, zip contents), and CloudFormation (create,
  status polling to `CREATE_COMPLETE`, update path, bundled template
  validity) — all running fully offline against `moto`'s mocked AWS APIs,
  so no AWS credentials or network access are required.
- CI (`.github/workflows/tests.yml`) running the suite on Python 3.11 and
  3.12, plus an MIT license and a bundled example CloudFormation template
  (`templates/basic_stack.yaml`).
