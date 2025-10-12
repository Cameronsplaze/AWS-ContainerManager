
import boto3

def setup_moto_network(region: str = "us-west-2"):
    ec2_client = boto3.client('ec2', region_name=region)
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2/client/create_vpc.html
    vpc = ec2_client.create_vpc(CidrBlock="192.168.0.0/16")["Vpc"]
    ## Create an internet gateway and attach it to the VPC, so instances can get public IPs:
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2/client/create_internet_gateway.html
    internet_gateway = ec2_client.create_internet_gateway()["InternetGateway"]
    ec2_client.attach_internet_gateway(InternetGatewayId=internet_gateway["InternetGatewayId"], VpcId=vpc["VpcId"])
    ## Create a route table and a public route:
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2/client/create_route_table.html
    route_table = ec2_client.create_route_table(VpcId=vpc["VpcId"])["RouteTable"]
    ec2_client.create_route(
        RouteTableId=route_table["RouteTableId"],
        DestinationCidrBlock="0.0.0.0/0",
        GatewayId=internet_gateway["InternetGatewayId"],
    )
    ## Create a subnet:
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2/client/create_subnet.html
    subnet = ec2_client.create_subnet(VpcId=vpc["VpcId"], CidrBlock="192.168.1.0/24")["Subnet"]
    ec2_client.associate_route_table(
        RouteTableId=route_table["RouteTableId"],
        SubnetId=subnet["SubnetId"],
    )

    return vpc, subnet

def setup_autoscaling_group(asg_name: str):
        ## Override the lambda's boto3 client(s) here, to make sure moto mocks them:
        #    (All moto clients have to be in-scope, together. They'll error if in setup_class.)
        # moto: https://docs.getmoto.org/en/latest/docs/services/autoscaling.html
        # boto: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/autoscaling.html
        asg_client = boto3.client('autoscaling', region_name="us-west-2")
        _vpc, subnet = setup_moto_network() # This has a moto/boto inside it.
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