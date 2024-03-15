

from constructs import Construct
from aws_cdk import (
    Stack,
    CfnParameter,
    Tags,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_iam as iam,
    aws_autoscaling as autoscaling,
    aws_route53 as route53,
)

from .get_param import get_param

class ContainerManagerBaseStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.domain_name = get_param(self, "DOMAIN_NAME")

        #################
        ### VPC STUFF ###
        #################
        # Create a Public VPC to run instances in:
        self.vpc = ec2.Vpc(
            self,
            f"{construct_id}-VPC",
            nat_gateways=0,
            max_azs=2,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name=f"public-{construct_id}-sn",
                    subnet_type=ec2.SubnetType.PUBLIC,
                )
            ]
        )

        ## VPC Security Group - Traffic in/out the VPC itself:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2.SecurityGroup.html
        self.sg_vpc_traffic = ec2.SecurityGroup(
            self,
            f"{construct_id}-sg-vpc-traffic",
            description="Traffic for the VPC itself",
            vpc=self.vpc,
            allow_all_outbound=False
        )
        Tags.of(self.sg_vpc_traffic).add("Name", f"{construct_id}/sg-vpc-traffic")
        self.sg_vpc_traffic.connections.allow_to(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(443),
            # - Let ECS talk with EC2 to register instances (Maybe only required for private ecs)
            # - Let any games curl out to the internet to download stuff
            # - Let containers update if you run `yum update` or `apt-get update`
            description="Allow HTTPS traffic OUT",
        )

        #####################
        ### Route53 STUFF ###
        #####################

        # Create a Route53 Hosted Zone:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_route53.PrivateHostedZone.html
        # NOTE: This maybe dynamic based on variables you set. If you register a domain in
        # AWS, it creates a hosted zone automatically.
        # NOTE 2: Testing out private first, it's the only one that you can add to a vpc.
        self.hosted_zone = route53.PrivateHostedZone(
            self,
            f"{construct_id}-hosted-zone",
            zone_name=self.domain_name,
            vpc=self.vpc,
            comment=f"Hosted zone for {construct_id}: {self.domain_name}",
        )
        # self.hosted_zone = route53.PublicHostedZone(
        #     self,
        #     f"{construct_id}-hosted-zone",
        #     zone_name=self.domain_name,
        #     comment=f"Hosted zone for {construct_id}: {self.domain_name}",
        # )
        # NOTE: ONLY apply this if you just created the hosted zone!!!
        self.hosted_zone.apply_removal_policy(RemovalPolicy.DESTROY)

        ## Update DNS for the VPC
        # (TODO: Test if you need this if it's a public hosted zone)
        for port in [ec2.Port.udp(53), ec2.Port.tcp(53)]:
            self.sg_vpc_traffic.connections.allow_from(
                ec2.Peer.any_ipv4(),
                port_range=port,
                description="Allow DNS traffic from outside"
            )
