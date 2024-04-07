

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

        self.root_hosted_zone_id = get_param(self, "HOSTED_ZONE_ID", default=None)
        self.domain_name = str(get_param(self, "DOMAIN_NAME")).lower()
        self.alert_email = get_param(self, "EMAIL", default=None)

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

        ########################
        ### SNS Notify STUFF ###
        ########################
        # ONLY if they give us a email to notify:
        if self.alert_email:
            ## Create an SNS Topic for notifications:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_sns.Topic.html
            self.sns_notify_topic = sns.Topic(
                self,
                f"{construct_id}-sns-notify-topic",
                display_name=f"{construct_id}-sns-notify-topic",
            )

            ## Email with a SNS Subscription:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_sns.Subscription.html
            self.sns_notify_subscription = sns.Subscription(
                self,
                f"{construct_id}-sns-notify-subscription",
                protocol=sns.SubscriptionProtocol.EMAIL,
                endpoint=self.alert_email,
                topic=self.sns_notify_topic,
            )


        #####################
        ### Route53 STUFF ###
        #####################

        if self.root_hosted_zone_id:
            ## Import the existing Route53 Hosted Zone:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_route53.PublicHostedZoneAttributes.html
            self.root_hosted_zone = route53.PublicHostedZone.from_hosted_zone_attributes(
                self,
                f"{construct_id}-hosted-zone",
                hosted_zone_id=self.root_hosted_zone_id,
                zone_name=self.domain_name,
            )
        else:
            ## Create a Route53 Hosted Zone:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_route53.PublicHostedZone.html
            self.root_hosted_zone = route53.PublicHostedZone(
                self,
                f"{construct_id}-hosted-zone",
                zone_name=self.domain_name,
                comment=f"Hosted zone for {construct_id}: {self.domain_name}",
            )
            self.root_hosted_zone.apply_removal_policy(RemovalPolicy.DESTROY)

        ## Update DNS for the VPC
        # (TODO: Test if you need this if it's a public hosted zone)
        for port in [ec2.Port.udp(53), ec2.Port.tcp(53)]:
            self.sg_vpc_traffic.connections.allow_from(
                ec2.Peer.any_ipv4(),
                port_range=port,
                description="Allow DNS traffic from outside"
            )
