
from moto import mock_aws
import pytest

## These imports have to be the long forum, to let us modify the values here:
# https://stackoverflow.com/a/12496239/11650472
import ContainerManager.leaf_stack_group.lambda_functions.spin_down_asg_on_error.main as spin_down_asg_on_error

from .utils import setup_autoscaling_group


## This seems promising for when re-doing lambda's env vars, and importing the file here:
# https://ranthebuilder.medium.com/aws-lambda-environment-variables-best-practices-f760384c23ed

@mock_aws
class TestSpinDownASGOnError:
    @classmethod
    def setup_class(cls):
        ## DON'T use boto3.clients here. The resources they create, won't reset between each test.
        cls.env = {
            "ASG_NAME": "test-asg"
        }

    def setup_method(self, _method):
        # Reset everything, so each test is a "cold start":
        spin_down_asg_on_error.get_env_vars.cache_clear()
        spin_down_asg_on_error.get_asg_client.cache_clear()

        setup_autoscaling_group(
            self.env["ASG_NAME"],
        )
        self.asg_client = spin_down_asg_on_error.get_asg_client() # pylint: disable=attribute-defined-outside-init

    def test_asg_starting_state(self, setup_env):
        """Test that the ASG starts with the correct state."""
        setup_env(self.env)
        asg = self.asg_client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[self.env["ASG_NAME"]],
        )["AutoScalingGroups"][0]
        assert asg["DesiredCapacity"] == 1
        assert asg["MinSize"] == 0
        assert asg["MaxSize"] == 1

    @pytest.mark.parametrize("starting_capacity", [0, 1])
    def test_lambda_spins_down_asg(self, setup_env, starting_capacity):
        """Test that the lambda spins down the ASG to 0, regardless of starting capacity."""
        # First, update the ASG:
        setup_env(self.env)
        self.asg_client.update_auto_scaling_group(
            AutoScalingGroupName=self.env["ASG_NAME"],
            DesiredCapacity=starting_capacity,
        )
        # Make sure it's set:
        asg_info = self.asg_client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[self.env["ASG_NAME"]],
        )["AutoScalingGroups"][0]
        assert asg_info["DesiredCapacity"] == starting_capacity

        # Call the lambda:
        spin_down_asg_on_error.lambda_handler(event={}, context={})

        # Check if the ASG Is spun down (DesiredCapacity = 0):
        asg_info = self.asg_client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[self.env["ASG_NAME"]],
        )["AutoScalingGroups"][0]
        assert asg_info["DesiredCapacity"] == 0
