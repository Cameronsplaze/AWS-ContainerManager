
import json

from moto import mock_aws

## This has to be the full path, to let us modify the values here:
# https://stackoverflow.com/a/12496239/11650472
import ContainerManager.leaf_stack_group.lambda_functions.trigger_start_system.main as trigger_start_system

@mock_aws
class TestTriggerStartSystem:
    @classmethod
    def setup_class(cls):
        ## DON'T use boto3.clients here. The resources they create, won't reset between each test.
        cls.env = {
            "ASG_NAME": "test-asg",
            "MANAGER_STACK_REGION": "us-west-2",
            # For not letting the system spin down if someone is trying to connect:
            "METRIC_NAMESPACE": "test-namespace",
            "METRIC_NAME": "test-metric",
            "METRIC_THRESHOLD": "1",
            "METRIC_UNIT": "Count",
            "METRIC_DIMENSIONS": json.dumps({
                "ContainerNameID": "test-stack",
            }),
        }

    def setup_method(self, _method):
        # Reset the env vars, so each test is a "cold start":
        trigger_start_system.get_env_vars.cache_clear()
        # And reset the boto3 clients:
        trigger_start_system.get_cloudwatch_client.cache_clear()
        trigger_start_system.get_asg_client.cache_clear()

        ## CAN'T Create shared clients here. They have to be initialized
        # after the `setup_env` call in each test, so the env-vars exist.

    def test_stuff(self, setup_env):
        setup_env(self.env)
        _cloudwatch_client = trigger_start_system.get_cloudwatch_client()
        _asg_client = trigger_start_system.get_asg_client()
        assert True, "Add real tests here."
