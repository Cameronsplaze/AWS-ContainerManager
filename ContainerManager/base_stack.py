

from constructs import Construct
from aws_cdk import (
    Stack,
    Tags,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_route53 as route53,
    aws_sns as sns,
    aws_servicecatalogappregistry as appregistry,
)

# from .utils.get_param import get_param
from .utils.sns_subscriptions import add_sns_subscriptions

class ContainerManagerBaseStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, config: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        #################
        ### VPC STUFF ###
        #################

        # ### Create a VPC log group:
        # # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_logs.LogGroup.html
        # self.log_group_vpc = logs.LogGroup(
        #     self,
        #     "log-group-vpc",
        #     log_group_name=f"/{construct_id}/vpc",
        #     retention=logs.RetentionDays.ONE_WEEK,
        #     removal_policy=RemovalPolicy.DESTROY,
        # )

        ### Create a Public VPC to run instances in:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2.Vpc.html
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
            ],
        )
        # # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2.FlowLogOptions.html
        # self.vpc.add_flow_log("vpc-flow-log-reject",
        #     destination=ec2.FlowLogDestination.to_cloud_watch_logs(
        #         log_group=self.log_group_vpc,
        #     ),
        #     traffic_type=ec2.FlowLogTrafficType.REJECT,
        #     # traffic_type=ec2.FlowLogTrafficType.ALL,
        # )

        ## VPC Security Group - Traffic in/out the VPC itself:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2.SecurityGroup.html
        # TODO: I don't think this is actually being used? It's not attached to the VPC anywhere,
        #       and no objects use it down the line. Maybe it's supposed to be the vpc_default_security_group?
        #         - https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2.Vpc.html#vpcdefaultsecuritygroup
        # self.sg_vpc_traffic = ec2.SecurityGroup(
        #     self,
        #     "sg-vpc-traffic",
        #     description="Traffic for the VPC itself",
        #     vpc=self.vpc,
        #     # allow_all_outbound=False
        # )
        # Tags.of(self.sg_vpc_traffic).add("Name", f"{construct_id}/sg-vpc-traffic")
        # self.sg_vpc_traffic.connections.allow_to(
        #     ec2.Peer.any_ipv4(),
        #     ec2.Port.tcp(443),
        #     # - Let ECS talk with EC2 to register instances (Maybe only required for private ecs)
        #     # - Let any container curl out to the internet to download stuff
        #     # - Let containers update if you run `yum update` or `apt-get update`
        #     description="Allow HTTPS traffic OUT",
        # )
        # ## Allow SSH traffic:
        # self.sg_vpc_traffic.connections.allow_from(
        #     ec2.Peer.any_ipv4(),
        #     ec2.Port.tcp(22),
        #     description="Allow SSH traffic IN",
        # )
        ## For enabling SSH access:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2.KeyPair.html
        self.ssh_key_pair = ec2.KeyPair(
            self,
            "ssh-key-pair",
            ### To import a Public Key:
            # TODO: Maybe use get_param to optionally import this?
            # public_key_material="ssh-rsa ABCD...",
            # And/Or maybe set an optional one in each leaf-stack? If set, overrides this?
            public_key_material=None,
        )
        ## Private key generated from the KeyPair:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ssm.StringParameter.html
        # TODO: Can't get these to work. Asked about it at: https://github.com/aws/aws-cdk/discussions/30049
        Tags.of(self.ssh_key_pair.private_key).add("ssh_key_pair_id", self.ssh_key_pair.key_pair_name)
        Tags.of(self.ssh_key_pair.private_key).add("Stack", construct_id)

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
