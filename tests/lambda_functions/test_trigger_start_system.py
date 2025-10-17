import boto3
from moto import mock_aws

## This has to be the full path, to let us modify the values here:
# https://stackoverflow.com/a/12496239/11650472
import ContainerManager.leaf_stack_group.lambda_functions.trigger_start_system.main as trigger_start_system

@mock_aws
class TestTriggerStartSystem:
    @classmethod
    def setup_class(cls):
        ## DON'T use boto3.clients here. The resources they create, won't reset between each test.
        cls.env = {}

    def setup_method(self, _method):
        # Reset the env vars, so each test is a "cold start":
        trigger_start_system._env_vars = None # pylint: disable=protected-access
        ## Override the lambda's boto3 client(s) here, to make sure moto mocks them:
        #    (All moto clients have to be in-scope, together. They'll error if in setup_class.)
        trigger_start_system.cloudwatch_client = boto3.client('cloudwatch', region_name="us-west-2")
        trigger_start_system.asg_client = boto3.client('autoscaling', region_name="us-west-2")
