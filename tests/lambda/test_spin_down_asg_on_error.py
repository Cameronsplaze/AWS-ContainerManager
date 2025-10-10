
import os

import boto3
from moto import mock_aws
import pytest

### AutoScaling Moto/Boto Docs:
# moto: https://docs.getmoto.org/en/latest/docs/services/autoscaling.html
# boto: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/autoscaling.html


def setup_moto_network(region: str = "us-west-2"):
    ec2_client = boto3.client('ec2', region_name=region)
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2/client/create_vpc.html
    vpc = ec2_client.create_vpc(CidrBlock="10.0.0.0/16")["Vpc"]
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2/client/create_subnet.html
    subnet = ec2_client.create_subnet(VpcId=vpc["VpcId"], CidrBlock="10.0.1.0/24")["Subnet"]
    return vpc, subnet

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
        ## Override the lambda's boto3 client(s) here, to make sure moto mocks them:
        #    (All moto clients have to be in-scope, together. They'll error if in setup_class.)
        self.spin_down_asg_on_error.asg_client = boto3.client('autoscaling', region_name="us-west-2")
        _vpc, subnet = setup_moto_network() # This has a moto/boto inside it.
        ## Create a very basic launch template:
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/autoscaling/client/create_launch_configuration.html
        launch_config_name = "test-launch-config"
        self.spin_down_asg_on_error.asg_client.create_launch_configuration(
            LaunchConfigurationName=launch_config_name,
            ImageId="ami-12345678",
            InstanceType="t2.micro",
        )
        ## Create a ASG for each test:
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/autoscaling/client/create_auto_scaling_group.html
        self.spin_down_asg_on_error.asg_client.create_auto_scaling_group(
            AutoScalingGroupName=os.environ["ASG_NAME"],
            MinSize=0,
            MaxSize=1,
            DesiredCapacity=1,
            LaunchConfigurationName=launch_config_name,
            VPCZoneIdentifier=subnet["SubnetId"],
        )

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
        assert asg["MinSize"] == 0
        assert asg["MaxSize"] == 1

        # Call the lambda:
        self.spin_down_asg_on_error.lambda_handler(event={}, context={})

        # Check if the ASG is still down:
        asg = self.spin_down_asg_on_error.asg_client.describe_auto_scaling_groups(
            AutoScalingGroupNames=[os.environ["ASG_NAME"]],
        )["AutoScalingGroups"][0]
        assert asg["DesiredCapacity"] == 0
        assert asg["MinSize"] == 0
        assert asg["MaxSize"] == 1
