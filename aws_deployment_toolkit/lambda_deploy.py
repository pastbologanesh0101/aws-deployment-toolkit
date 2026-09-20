"""Package a local directory and deploy it as an AWS Lambda function.

If the function does not exist yet, it is created. If it already exists,
only its code (and, optionally, its configuration) is updated. This mirrors
the common "create-or-update" deployment pattern used by real deployment
tools, without requiring any external packaging system.
"""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path

import boto3
from botocore.exceptions import ClientError


def zip_directory(source_dir: str) -> bytes:
    """Zip up a local directory's contents (not the directory itself)."""
    source_path = Path(source_dir)
    if not source_path.is_dir():
        if source_path.exists():
            raise FileNotFoundError(
                f"Expected a directory but found a file: {source_dir}"
            )
        raise FileNotFoundError(f"Local directory does not exist: {source_dir}")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(source_path):
            for name in files:
                full = Path(root) / name
                arcname = full.relative_to(source_path).as_posix()
                zf.write(full, arcname)
    buffer.seek(0)
    return buffer.read()


class LambdaDeployer:
    """Creates or updates a Lambda function from a local source directory."""

    def __init__(self, lambda_client=None, region_name: str | None = None):
        self.client = lambda_client or boto3.client("lambda", region_name=region_name)

    def function_exists(self, function_name: str) -> bool:
        try:
            self.client.get_function(FunctionName=function_name)
            return True
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code == "ResourceNotFoundException":
                return False
            raise

    def deploy(
        self,
        function_name: str,
        source_dir: str,
        handler: str = "handler.main",
        runtime: str = "python3.12",
        role_arn: str = "arn:aws:iam::123456789012:role/lambda-role",
        memory_size: int = 128,
        timeout: int = 30,
        environment: dict | None = None,
    ) -> dict:
        """Create the function if missing, otherwise update its code+config.

        Returns a dict with keys: action ("created" or "updated") and the
        raw boto3 response for the code deployment call.
        """
        zip_bytes = zip_directory(source_dir)

        if not self.function_exists(function_name):
            kwargs = dict(
                FunctionName=function_name,
                Runtime=runtime,
                Role=role_arn,
                Handler=handler,
                Code={"ZipFile": zip_bytes},
                MemorySize=memory_size,
                Timeout=timeout,
                Publish=True,
            )
            if environment is not None:
                kwargs["Environment"] = {"Variables": environment}
            response = self.client.create_function(**kwargs)
            return {"action": "created", "response": response}

        code_response = self.client.update_function_code(
            FunctionName=function_name,
            ZipFile=zip_bytes,
            Publish=True,
        )
        config_kwargs = dict(
            FunctionName=function_name,
            Handler=handler,
            Runtime=runtime,
            MemorySize=memory_size,
            Timeout=timeout,
        )
        if environment is not None:
            config_kwargs["Environment"] = {"Variables": environment}
        self.client.update_function_configuration(**config_kwargs)
        return {"action": "updated", "response": code_response}


def deploy_function(function_name: str, source_dir: str, **kwargs) -> dict:
    """Convenience function wrapping LambdaDeployer for CLI use."""
    deployer = LambdaDeployer()
    return deployer.deploy(function_name, source_dir, **kwargs)
