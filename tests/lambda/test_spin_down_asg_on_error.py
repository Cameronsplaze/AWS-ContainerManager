
import os

import boto3
from moto import mock_aws

### AutoScaling Moto/Boto Docs:
# moto: https://docs.getmoto.org/en/latest/docs/services/autoscaling.html
# boto: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/autoscaling.html


def setup_moto_network(ec2_client: boto3.client):
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
        import ContainerManager.leaf_stack_group.lambda_functions.spin_down_asg_on_error.main as spin_down_asg_on_error # pylint: disable # type: ignore
        # Override the lambda's boto3 client(s) here, to make sure moto mocks them:
        spin_down_asg_on_error.asg_client = boto3.client('autoscaling', region_name="us-west-2") # type: ignore
        cls.spin_down_asg_on_error = spin_down_asg_on_error
        cls.asg_client = cls.spin_down_asg_on_error.asg_client
        # Must create this client here, so it's in scope with the autoscaling client.
        cls.ec2_client = boto3.client('ec2', region_name="us-west-2")
        cls.asg_name = os.environ["ASG_NAME"]

    @classmethod
    def teardown_class(cls):
        # Remove the env var we set:
        del os.environ["ASG_NAME"]

    def setup_method(self, method):
        ## Setup info for each test:
        # Can't be in setup_class, or it'll go out of scope before this point.
        vpc, subnet = setup_moto_network(self.ec2_client)
        ## Create a very basic launch template:
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/autoscaling/client/create_launch_configuration.html
        launch_config_name = "test-launch-config"
        self.asg_client.create_launch_configuration(
            LaunchConfigurationName=launch_config_name,
            ImageId="ami-12345678",
            InstanceType="t2.micro",
        )
        ## Create a ASG for each test:
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/autoscaling/client/create_auto_scaling_group.html
        self.asg_client.create_auto_scaling_group(
            AutoScalingGroupName=self.asg_name,
            MinSize=0,
            MaxSize=1,
            DesiredCapacity=1,
            LaunchConfigurationName=launch_config_name,
            VPCZoneIdentifier=subnet["SubnetId"],
        )

    def test_spin_down_asg_on_error(self):
        # """ Test the lambda spins down the ASG. """
        asg = self.asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[self.asg_name])["AutoScalingGroups"][0]
        assert asg["DesiredCapacity"] == 1
        assert asg["MinSize"] == 0
        assert asg["MaxSize"] == 1

        # Call the lambda:
        self.spin_down_asg_on_error.lambda_handler(event={}, context={})

        # Check the ASG was spun down:
        asg = self.asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=["test-asg"])["AutoScalingGroups"][0]
        assert asg["DesiredCapacity"] == 0
        assert asg["MinSize"] == 0
        assert asg["MaxSize"] == 1

    def test_noop_if_asg_is_already_down(self):
        """ Test nothing changes if the ASG is already down. """
        # First, spin down the ASG:
        self.asg_client.update_auto_scaling_group(
            AutoScalingGroupName=self.asg_name,
            DesiredCapacity=0,
        )
        asg = self.asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[self.asg_name])["AutoScalingGroups"][0]
        assert asg["DesiredCapacity"] == 0
        assert asg["MinSize"] == 0
        assert asg["MaxSize"] == 1

        # Call the lambda:
        self.spin_down_asg_on_error.lambda_handler(event={}, context={})

        # Check the ASG is still down:
        asg = self.asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[self.asg_name])["AutoScalingGroups"][0]
        assert asg["DesiredCapacity"] == 0
        assert asg["MinSize"] == 0
        assert asg["MaxSize"] == 1