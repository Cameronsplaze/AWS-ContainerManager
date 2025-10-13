
import boto3


def setup_autoscaling_group(asg_name: str):
        ## Override the lambda's boto3 client(s) here, to make sure moto mocks them:
        #    (All moto clients have to be in-scope, together. They'll error if in setup_class.)
        # moto: https://docs.getmoto.org/en/latest/docs/services/autoscaling.html
        # boto: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/autoscaling.html
        asg_client = boto3.client('autoscaling', region_name="us-west-2")
       # moto: https://docs.getmoto.org/en/latest/docs/services/ec2.html
        # boto: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2.html
        ec2_client = boto3.client('ec2', region_name="us-west-2")
        # Use the Mock Default VPC's first subnet:
        subnet = ec2_client.describe_subnets()["Subnets"][0]
        ## Create a very basic launch template:
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/autoscaling/client/create_launch_configuration.html
        launch_config_name = "test-launch-config"
        asg_client.create_launch_configuration(
            LaunchConfigurationName=launch_config_name,
            ImageId="ami-12345678",
            InstanceType="t2.micro",
        )
        ## Create a ASG for each test:
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/autoscaling/client/create_auto_scaling_group.html
        asg_info = asg_client.create_auto_scaling_group(
            AutoScalingGroupName=asg_name,
            MinSize=0,
            MaxSize=1,
            DesiredCapacity=1,
            LaunchConfigurationName=launch_config_name,
            VPCZoneIdentifier=subnet["SubnetId"],
        )
        return asg_client, asg_info
