
import os

from moto import mock_aws
import pytest

from .utils import setup_autoscaling_group


## This seems promising for when re-doing lambda's env vars, and importing the file here:
# https://ranthebuilder.medium.com/aws-lambda-environment-variables-best-practices-f760384c23ed

@mock_aws
class TestSpinDownASGOnError:
    @classmethod
    def setup_class(cls):
        os.environ["ASG_NAME"] = "test-asg"
        ## These imports have to be the long forum, to let us modify the values here:
        # https://stackoverflow.com/a/12496239/11650472
        import ContainerManager.leaf_stack_group.lambda_functions.spin_down_asg_on_error.main as spin_down_asg_on_error # pylint: disable=import-outside-toplevel # type: ignore
        cls.spin_down_asg_on_error = spin_down_asg_on_error

    @classmethod
    def teardown_class(cls):
        # Remove the env var we set:
        del os.environ["ASG_NAME"]

    def setup_method(self, _method):
        self.spin_down_asg_on_error.asg_client, _ = setup_autoscaling_group(
            os.environ["ASG_NAME"],
        )

    def test_asg_starting_state(self):
        """Test that the ASG starts with the correct state."""
        asg = self.spin_down_asg_on_error.asg_client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[os.environ["ASG_NAME"]],
        )["AutoScalingGroups"][0]
        assert asg["DesiredCapacity"] == 1
        assert asg["MinSize"] == 0
        assert asg["MaxSize"] == 1

    @pytest.mark.parametrize("starting_capacity", [0, 1])
    def test_lambda_spins_down_asg(self, starting_capacity):
        """Test that the lambda spins down the ASG to 0, regardless of starting capacity."""
        # First, update the ASG:
        self.spin_down_asg_on_error.asg_client.update_auto_scaling_group(
            AutoScalingGroupName=os.environ["ASG_NAME"],
            DesiredCapacity=starting_capacity,
        )
        # Make sure it's set:
        asg = self.spin_down_asg_on_error.asg_client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[os.environ["ASG_NAME"]],
        )["AutoScalingGroups"][0]
        assert asg["DesiredCapacity"] == starting_capacity

        # Call the lambda:
        self.spin_down_asg_on_error.lambda_handler(event={}, context={})

        # Check if the ASG is still down:
        asg = self.spin_down_asg_on_error.asg_client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[os.environ["ASG_NAME"]],
        )["AutoScalingGroups"][0]
        assert asg["DesiredCapacity"] == 0
