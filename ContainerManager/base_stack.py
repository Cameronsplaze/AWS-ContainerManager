

from constructs import Construct
from aws_cdk import (
    Stack,
    Tags,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_route53 as route53,
    aws_sns as sns,
)

# from .utils.get_param import get_param
from .utils.sns_subscriptions import add_sns_subscriptions

class ContainerManagerBaseStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, config: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        #################
        ### VPC STUFF ###
        #################
        # Create a Public VPC to run instances in:
        self.vpc = ec2.Vpc(
            self,
            "VPC",
            nat_gateways=0,
            max_azs=config.get("MaxAZs", 1),
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
            "sg-vpc-traffic",
            description="Traffic for the VPC itself",
            vpc=self.vpc,
            allow_all_outbound=False
        )
        Tags.of(self.sg_vpc_traffic).add("Name", f"{construct_id}/sg-vpc-traffic")
        self.sg_vpc_traffic.connections.allow_to(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(443),
            # - Let ECS talk with EC2 to register instances (Maybe only required for private ecs)
            # - Let any container curl out to the internet to download stuff
            # - Let containers update if you run `yum update` or `apt-get update`
            description="Allow HTTPS traffic OUT",
        )

        ########################
        ### SNS Notify STUFF ###
        ########################

        ## Create an SNS Topic for notifications:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_sns.Topic.html
        self.sns_notify_topic = sns.Topic(
            self,
            "sns-notify-topic",
            display_name=f"{construct_id}-sns-notify-topic",
        )
        subscriptions = config.get("AlertSubscription", [])
        add_sns_subscriptions(self, self.sns_notify_topic, subscriptions)


        #####################
        ### Route53 STUFF ###
        #####################
        if "Domain" not in config:
            raise ValueError("Required key 'Domain' missing from config. See TODO on writing configs")
        if "Name" not in config["Domain"]:
            raise ValueError("Required key 'Domain.Name' missing from config. See TODO on writing configs")

        self.domain_name = str(config["Domain"]["Name"]).lower()
        self.root_hosted_zone_id = config["Domain"].get("HostedZoneId")

        if self.root_hosted_zone_id:
            ## Import the existing Route53 Hosted Zone:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_route53.PublicHostedZoneAttributes.html
            self.root_hosted_zone = route53.PublicHostedZone.from_hosted_zone_attributes(
                self,
                "root-hosted-zone",
                hosted_zone_id=self.root_hosted_zone_id,
                zone_name=self.domain_name,
            )
        else:
            ## Create a Route53 Hosted Zone:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_route53.PublicHostedZone.html
            self.root_hosted_zone = route53.PublicHostedZone(
                self,
                "root-hosted-zone",
                zone_name=self.domain_name,
                comment=f"Hosted zone for {construct_id}: {self.domain_name}",
            )
            self.root_hosted_zone.apply_removal_policy(RemovalPolicy.DESTROY)
