"""AWS Deployment Toolkit.

A small CLI toolkit for common AWS deployment operations:

- S3 incremental directory sync (hash/ETag based, with dry-run preview)
- Lambda function packaging + create-or-update deploy
- CloudFormation stack create-or-update + status polling

All AWS calls go through boto3, so the toolkit works against real AWS
when given real credentials, and against moto's in-memory mocked AWS
services in the test suite.
"""

__version__ = "0.1.0"
