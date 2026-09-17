from moto import mock_aws

from aws_deployment_toolkit.cloudformation import CloudFormationDeployer, load_bundled_template

REGION = "us-east-1"


@mock_aws
def test_deploy_creates_new_stack():
    deployer = CloudFormationDeployer(region_name=REGION)
    stack_name = "toolkit-test-stack"

    assert not deployer.stack_exists(stack_name)
    result = deployer.deploy(stack_name)

    assert result["action"] == "created"
    assert deployer.stack_exists(stack_name)


@mock_aws
def test_status_polling_reports_create_complete():
    deployer = CloudFormationDeployer(region_name=REGION)
    stack_name = "toolkit-status-stack"

    deployer.deploy(stack_name)
    status = deployer.wait_for_completion(stack_name, poll_interval=0.01, timeout=30)

    assert status == "CREATE_COMPLETE"
    assert deployer.get_status(stack_name) == "CREATE_COMPLETE"


@mock_aws
def test_update_existing_stack_path():
    deployer = CloudFormationDeployer(region_name=REGION)
    stack_name = "toolkit-update-stack"

    first = deployer.deploy(stack_name, parameters={"TopicDisplayName": "InitialTopic"})
    assert first["action"] == "created"
    deployer.wait_for_completion(stack_name, poll_interval=0.01, timeout=30)

    second = deployer.deploy(stack_name, parameters={"TopicDisplayName": "UpdatedTopic"})
    assert second["action"] in ("updated", "no_updates")


def test_bundled_template_loads_and_is_valid_yaml():
    body = load_bundled_template()
    assert "AWS::S3::Bucket" in body
    assert "AWS::SNS::Topic" in body
