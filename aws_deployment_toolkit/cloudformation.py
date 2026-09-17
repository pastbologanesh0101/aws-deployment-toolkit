"""Create-or-update deployment of the toolkit's bundled CloudFormation
template, plus a status-polling helper.

The bundled template (aws_deployment_toolkit/templates/basic_stack.yaml)
provisions an S3 bucket and an SNS topic. This module implements the
common "deploy" pattern: if the stack does not exist, create it; if it
does, update it (and treat "No updates are to be performed" as a
successful no-op rather than an error).
"""

from __future__ import annotations

import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

TEMPLATE_PATH = Path(__file__).parent / "templates" / "basic_stack.yaml"

TERMINAL_SUCCESS_STATUSES = {"CREATE_COMPLETE", "UPDATE_COMPLETE"}
TERMINAL_FAILURE_STATUSES = {
    "CREATE_FAILED",
    "ROLLBACK_COMPLETE",
    "ROLLBACK_FAILED",
    "UPDATE_ROLLBACK_COMPLETE",
    "UPDATE_ROLLBACK_FAILED",
    "DELETE_FAILED",
}


def load_bundled_template(path: Path | str = TEMPLATE_PATH) -> str:
    return Path(path).read_text()


class CloudFormationDeployer:
    """Deploys the bundled (or a custom) template with create-or-update logic."""

    def __init__(self, cfn_client=None, region_name: str | None = None):
        self.client = cfn_client or boto3.client("cloudformation", region_name=region_name)

    def stack_exists(self, stack_name: str) -> bool:
        try:
            resp = self.client.describe_stacks(StackName=stack_name)
            stacks = resp.get("Stacks", [])
            if not stacks:
                return False
            return stacks[0]["StackStatus"] != "REVIEW_IN_PROGRESS"
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            message = exc.response.get("Error", {}).get("Message", "")
            if code == "ValidationError" or "does not exist" in message:
                return False
            raise

    def deploy(
        self,
        stack_name: str,
        template_body: str | None = None,
        parameters: dict | None = None,
    ) -> dict:
        """Create the stack if missing, otherwise update it.

        Returns {"action": "created"|"updated"|"no_updates", "stack_name": ...}.
        """
        body = template_body if template_body is not None else load_bundled_template()
        cfn_params = [
            {"ParameterKey": k, "ParameterValue": v} for k, v in (parameters or {}).items()
        ]

        if not self.stack_exists(stack_name):
            self.client.create_stack(
                StackName=stack_name,
                TemplateBody=body,
                Parameters=cfn_params,
                Capabilities=["CAPABILITY_NAMED_IAM"],
            )
            return {"action": "created", "stack_name": stack_name}

        try:
            self.client.update_stack(
                StackName=stack_name,
                TemplateBody=body,
                Parameters=cfn_params,
                Capabilities=["CAPABILITY_NAMED_IAM"],
            )
            return {"action": "updated", "stack_name": stack_name}
        except ClientError as exc:
            message = exc.response.get("Error", {}).get("Message", "")
            if "No updates are to be performed" in message:
                return {"action": "no_updates", "stack_name": stack_name}
            raise

    def get_status(self, stack_name: str) -> str:
        """Return the current StackStatus for a stack."""
        resp = self.client.describe_stacks(StackName=stack_name)
        return resp["Stacks"][0]["StackStatus"]

    def wait_for_completion(
        self,
        stack_name: str,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
    ) -> str:
        """Poll describe_stacks until the stack reaches a terminal status.

        Returns the final status string. Raises RuntimeError if a failure
        status is reached, and TimeoutError if the timeout elapses first.
        """
        start = time.time()
        while True:
            status = self.get_status(stack_name)
            if status in TERMINAL_SUCCESS_STATUSES:
                return status
            if status in TERMINAL_FAILURE_STATUSES:
                raise RuntimeError(f"Stack {stack_name} reached failure status: {status}")
            if time.time() - start > timeout:
                raise TimeoutError(f"Timed out waiting for stack {stack_name} (last status: {status})")
            time.sleep(poll_interval)


def deploy_bundled_stack(stack_name: str, parameters: dict | None = None) -> dict:
    """Convenience function wrapping CloudFormationDeployer for CLI use."""
    deployer = CloudFormationDeployer()
    return deployer.deploy(stack_name, parameters=parameters)
