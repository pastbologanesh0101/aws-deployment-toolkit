# AWS Deployment Toolkit

A small, focused command-line toolkit for common AWS deployment operations,
built on `boto3`. It implements three real deployment workflows correctly
rather than superficially:

- **S3 sync** — incrementally syncs a local directory to an S3 bucket.
  Files are compared by MD5 hash against the object's S3 ETag, so only
  *new* or *changed* files are uploaded; unchanged files are skipped. A
  `--dry-run` mode previews the plan without touching AWS.
- **Lambda deploy** — zips a local source directory in memory and
  creates the Lambda function if it doesn't exist, or updates its code
  (and configuration) if it does.
- **CloudFormation deploy** — deploys a bundled template (an S3 bucket +
  an SNS topic) using create-or-update logic, plus a status-polling
  helper that reports the stack's `StackStatus` until it reaches a
  terminal state.

## Why moto, and how testing works

This project was built and tested **without a real AWS account**. Every
AWS call goes through `boto3`, which means:

- **Against real AWS**: point the toolkit at real AWS credentials (via
  the standard `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_PROFILE`
  environment variables, or an EC2/Lambda instance role) and it will
  create real S3 buckets, deploy real Lambda functions, and manage real
  CloudFormation stacks. No code changes are required — boto3 picks up
  credentials automatically.
- **In the test suite**: every test uses [`moto`](https://github.com/getmoto/moto)'s
  `@mock_aws` decorator, which intercepts boto3's HTTP calls and serves
  them from an in-memory, API-compatible mock of S3, Lambda, IAM, and
  CloudFormation. No Docker container, no network access, and no AWS
  account are needed to run the tests — but the toolkit's *actual logic*
  (hash comparison, create-vs-update branching, status polling) runs for
  real against these mocked services, not against stubs of the toolkit
  itself. This is what makes the test suite meaningful: it proves the
  sync algorithm, the deploy branching, and the polling loop behave
  correctly against a real boto3 API surface.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
pip install -r requirements-dev.txt   # adds moto + pytest for testing
```

## CLI usage

```bash
# Preview an S3 sync without changing anything
adt s3-sync ./site my-bucket --dry-run

# Actually sync a local directory to a bucket (creates the bucket if missing)
adt s3-sync ./site my-bucket --prefix static/

# Deploy (create or update) a Lambda function from a local directory
adt lambda-deploy ./my_function my-function \
    --handler handler.main --runtime python3.12 --memory 256 --timeout 30

# Deploy the bundled CloudFormation template (S3 bucket + SNS topic)
adt cfn-deploy my-stack --param TopicDisplayName=MyNotifications --wait

# Check a stack's current status
adt cfn-status my-stack
```

Every command can also be used as a library:

```python
from aws_deployment_toolkit.s3_sync import S3Syncer

syncer = S3Syncer(region_name="us-east-1")
plan = syncer.sync("./site", "my-bucket", dry_run=True)
print(plan.summary())
```

## How the S3 sync algorithm works

1. List all objects currently in the bucket (if it exists) and record
   each object's `ETag`.
2. Walk the local directory recursively, computing the MD5 hash of each
   file's contents.
3. For a simple (non-multipart) upload — which is all this toolkit ever
   does — S3's ETag *is* the hex MD5 digest of the object body. So a
   file is:
   - **new**, if its key isn't in the bucket yet → uploaded
   - **changed**, if the local MD5 doesn't match the remote ETag → uploaded
   - **unchanged**, if the hashes match → skipped
4. In `--dry-run` mode, steps 1–3 run exactly the same way, but no
   bucket is created and no objects are uploaded — only the plan is
   returned/printed.

## Running the tests

```bash
pytest tests/ -v
```

The suite (`tests/`) covers, among other things:

- S3 sync uploading new files
- S3 sync skipping unchanged files (hash/ETag comparison logic)
- S3 sync uploading changed files
- Dry-run mode making no actual changes (bucket not created, object not overwritten)
- S3 bucket auto-creation when missing
- Lambda deploy creating a new function
- Lambda deploy updating an existing function's code and configuration
- CloudFormation stack creation + status polling reaching `CREATE_COMPLETE`
- CloudFormation update-existing-stack path
- Clean error handling for invalid input (nonexistent local directory)

All tests run fully offline via moto — no AWS credentials required.

## Continuous Integration

`.github/workflows/tests.yml` runs the full test suite on every push and
pull request against Python 3.11 and 3.12, using `actions/checkout@v4`
and `actions/setup-python@v5`. No AWS credentials are configured or
needed in CI, since moto mocks every AWS call.

## Project layout

```
aws_deployment_toolkit/
    cli.py              # click-based CLI entry point (`adt`)
    s3_sync.py          # S3 incremental sync logic
    lambda_deploy.py    # Lambda packaging + create-or-update deploy
    cloudformation.py   # CloudFormation create-or-update + status polling
    templates/
        basic_stack.yaml  # bundled example template (S3 bucket + SNS topic)
tests/
    test_s3_sync.py
    test_lambda_deploy.py
    test_cloudformation.py
```

## Troubleshooting / FAQ

**`adt lambda-deploy` fails with `InvalidParameterValueException` about the
execution role.** Lambda requires `--role-arn` to be a real IAM role whose
trust policy allows `lambda.amazonaws.com` to assume it. The `--role-arn`
default (`arn:aws:iam::123456789012:role/lambda-role`) is a placeholder
that only works against moto's mocked Lambda — against real AWS you must
pass a real role ARN you've created, e.g.
`--role-arn arn:aws:iam::<account-id>:role/<your-role>`.

**`adt cfn-deploy` says the stack was "updated" but nothing changed.**
CloudFormation returns "No updates are to be performed" when the template
and parameters are identical to the current stack state. The toolkit
treats that as a successful `no_updates` action rather than an error —
check the printed action (`created` / `updated` / `no_updates`) if you
need to distinguish a real update from a no-op.

**`adt s3-sync` re-uploads a file every time even though its content
hasn't changed.** This can happen for objects that were uploaded outside
the toolkit as *multipart* uploads (common above ~8MB via some tools or
the S3 console) — a multipart object's ETag is not a plain MD5 of its
body, so it will never match the local MD5 the toolkit computes, and every
sync will treat it as changed. Files the toolkit itself uploads always use
a single-part `upload_file` call and aren't affected; only pre-existing
multipart objects hit this.

## License

MIT — see [LICENSE](LICENSE).
