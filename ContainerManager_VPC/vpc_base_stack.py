

from constructs import Construct
from aws_cdk import (
    Stack,
    CfnParameter,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_iam as iam,
    aws_autoscaling as autoscaling,
)


class VpcBaseStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        print(f"Stack: {Stack.of(self).account}")

        # Create a Public VPC to run instances in:
        self.vpc = ec2.Vpc(
            self,
            "Vpc",
            nat_gateways=0,
            max_azs=2,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name=f"public-{construct_id}",
                    subnet_type=ec2.SubnetType.PUBLIC,
                )
            ]
        )

        ## ECS / EC2 Security Group (Same since using bridge I think?):
        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_ec2/SecurityGroup.html
        self.sg_vpc_traffic = ec2.SecurityGroup(
            self,
            "sg-vpc-traffic",
            description="Traffic for the VPC itself",
            vpc=self.vpc,
            allow_all_outbound=False
        )
        self.sg_vpc_traffic.connections.allow_to(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(443),
            description="Allow HTTPS traffic OUT. Let ECS talk with EC2 to register instances",
        )
        # self.sg_vpc_traffic.connections.allow_to(
        #     ec2.Peer.any_ipv4(),
        #     ec2.Port.tcp(2049),
        #     description="Allow EFS traffic OUT. Let ECS talk with EFS for persistent storage",
        # )
