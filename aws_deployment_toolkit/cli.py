"""Command-line interface for the AWS Deployment Toolkit.

Examples
--------
    # Preview an S3 sync without changing anything
    adt s3-sync ./site my-bucket --dry-run

    # Actually sync a local directory to a bucket
    adt s3-sync ./site my-bucket --prefix static/

    # Deploy (create or update) a Lambda function from a local directory
    adt lambda-deploy ./my_function my-function --handler handler.main --runtime python3.12

    # Deploy the bundled CloudFormation template (S3 bucket + SNS topic)
    adt cfn-deploy my-stack --wait
"""

from __future__ import annotations

import sys

import click

from .cloudformation import CloudFormationDeployer
from .lambda_deploy import LambdaDeployer
from .s3_sync import S3Syncer


@click.group()
@click.version_option(package_name="aws-deployment-toolkit")
def main():
    """AWS Deployment Toolkit: S3 sync, Lambda deploy, and CloudFormation deploy."""


@main.command("s3-sync")
@click.argument("local_dir")
@click.argument("bucket")
@click.option("--prefix", default="", help="Key prefix inside the bucket.")
@click.option("--dry-run", is_flag=True, help="Show what would change without uploading.")
@click.option("--region", default=None, help="AWS region.")
def s3_sync_cmd(local_dir, bucket, prefix, dry_run, region):
    """Sync LOCAL_DIR to BUCKET, uploading only new/changed files."""
    syncer = S3Syncer(region_name=region)
    try:
        plan = syncer.sync(local_dir, bucket, prefix=prefix, dry_run=dry_run)
    except FileNotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    if dry_run:
        click.echo("[DRY RUN] No changes were made. Plan:")
    else:
        click.echo("Sync complete. Summary:")
    click.echo(plan.summary())


@main.command("lambda-deploy")
@click.argument("source_dir")
@click.argument("function_name")
@click.option("--handler", default="handler.main", show_default=True)
@click.option("--runtime", default="python3.12", show_default=True)
@click.option("--role-arn", default="arn:aws:iam::123456789012:role/lambda-role", show_default=True)
@click.option("--memory", default=128, show_default=True, type=int)
@click.option("--timeout", default=30, show_default=True, type=int)
@click.option("--region", default=None, help="AWS region.")
def lambda_deploy_cmd(source_dir, function_name, handler, runtime, role_arn, memory, timeout, region):
    """Package SOURCE_DIR and create/update the Lambda FUNCTION_NAME."""
    deployer = LambdaDeployer(region_name=region)
    try:
        result = deployer.deploy(
            function_name,
            source_dir,
            handler=handler,
            runtime=runtime,
            role_arn=role_arn,
            memory_size=memory,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    click.echo(f"Lambda function '{function_name}' {result['action']}.")


@main.command("cfn-deploy")
@click.argument("stack_name")
@click.option("--param", multiple=True, help="Template parameter as KEY=VALUE. Repeatable.")
@click.option("--wait/--no-wait", default=True, help="Poll for completion after deploying.")
@click.option("--region", default=None, help="AWS region.")
def cfn_deploy_cmd(stack_name, param, wait, region):
    """Create or update the bundled CloudFormation stack STACK_NAME."""
    params = {}
    for item in param:
        if "=" not in item:
            click.echo(f"Error: --param must be KEY=VALUE, got: {item}", err=True)
            sys.exit(1)
        key, value = item.split("=", 1)
        params[key] = value

    deployer = CloudFormationDeployer(region_name=region)
    result = deployer.deploy(stack_name, parameters=params)
    click.echo(f"Stack '{stack_name}' {result['action']}.")

    if wait:
        status = deployer.wait_for_completion(stack_name)
        click.echo(f"Final status: {status}")


@main.command("cfn-status")
@click.argument("stack_name")
@click.option("--region", default=None, help="AWS region.")
def cfn_status_cmd(stack_name, region):
    """Print the current status of STACK_NAME."""
    deployer = CloudFormationDeployer(region_name=region)
    click.echo(deployer.get_status(stack_name))


if __name__ == "__main__":
    main()
