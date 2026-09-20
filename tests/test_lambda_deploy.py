import boto3
import pytest
from moto import mock_aws

from aws_deployment_toolkit.lambda_deploy import LambdaDeployer, zip_directory

REGION = "us-east-1"

ASSUME_ROLE_POLICY = """{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }
    ]
}"""


def _write_handler(tmp_path, body="def main(event, context):\n    return event\n"):
    (tmp_path / "handler.py").write_text(body)
    return tmp_path


def _make_execution_role(region=REGION):
    """Create a real (moto-mocked) IAM role Lambda is allowed to assume.

    Moto validates that a Lambda function's execution role has a trust
    policy permitting lambda.amazonaws.com to assume it, so tests create
    one via the mocked IAM service rather than passing an arbitrary ARN.
    """
    iam = boto3.client("iam", region_name=region)
    role = iam.create_role(
        RoleName="lambda-execution-role",
        AssumeRolePolicyDocument=ASSUME_ROLE_POLICY,
    )
    return role["Role"]["Arn"]


@mock_aws
def test_deploy_creates_new_function(tmp_path):
    _write_handler(tmp_path)
    role_arn = _make_execution_role()
    deployer = LambdaDeployer(region_name=REGION)
    function_name = "my-new-function"

    assert not deployer.function_exists(function_name)
    result = deployer.deploy(function_name, str(tmp_path), role_arn=role_arn)

    assert result["action"] == "created"
    assert deployer.function_exists(function_name)


@mock_aws
def test_deploy_updates_existing_function_code(tmp_path):
    _write_handler(tmp_path, "def main(event, context):\n    return 1\n")
    role_arn = _make_execution_role()
    deployer = LambdaDeployer(region_name=REGION)
    function_name = "my-updatable-function"

    first = deployer.deploy(function_name, str(tmp_path), role_arn=role_arn)
    assert first["action"] == "created"

    _write_handler(tmp_path, "def main(event, context):\n    return 2\n")
    second = deployer.deploy(
        function_name, str(tmp_path), role_arn=role_arn, memory_size=256, timeout=60
    )

    assert second["action"] == "updated"
    config = deployer.client.get_function_configuration(FunctionName=function_name)
    assert config["MemorySize"] == 256
    assert config["Timeout"] == 60


@mock_aws
def test_deploy_raises_clean_error_for_missing_source_dir():
    deployer = LambdaDeployer(region_name=REGION)
    with pytest.raises(FileNotFoundError):
        deployer.deploy("some-function", "/nonexistent/source/dir")


@mock_aws
def test_deploy_raises_specific_error_when_source_dir_is_a_file(tmp_path):
    file_path = tmp_path / "handler.py"
    file_path.write_text("def main(event, context):\n    return event\n")
    deployer = LambdaDeployer(region_name=REGION)
    with pytest.raises(FileNotFoundError, match="found a file"):
        deployer.deploy("some-function", str(file_path))


def test_zip_directory_contains_expected_files(tmp_path):
    _write_handler(tmp_path)
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "helper.py").write_text("x = 1\n")

    zip_bytes = zip_directory(str(tmp_path))

    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
    assert names == {"handler.py", "sub/helper.py"}
