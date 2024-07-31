
"""
This module contains the ContainerManagerBaseStack class.
"""

from constructs import Construct
from aws_cdk import (
    Stack,
    Tags,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_route53 as route53,
    aws_sns as sns,
    aws_iam as iam,
)

# from .utils.get_param import get_param
from .utils.sns_subscriptions import add_sns_subscriptions

class ContainerManagerBaseStack(Stack):
    """
    Contains shared resources for all leaf stacks.
    Most importantly, the VPC and SNS.
    """
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        config: dict,
        application_id_tag_name: str,
        application_id_tag_value: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        #################
        ### VPC STUFF ###
        #################

        ### Create a Public VPC to run instances in:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2.Vpc.html
        self.vpc = ec2.Vpc(
            self,
            "Vpc",
            nat_gateways=0,
            max_azs=config.get("MaxAZs", 1),
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name=f"public-{construct_id}-sn",
                    subnet_type=ec2.SubnetType.PUBLIC,
                )
            ],
        )

        ## For enabling SSH access:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2.KeyPair.html
        self.ssh_key_pair = ec2.KeyPair(
            self,
            "SshKeyPair",
            ### To import a Public Key:
            # TODO: Maybe use get_param to optionally import this?
            # public_key_material="ssh-rsa ABCD...",
            # And/Or maybe set an optional one in each leaf-stack? If set, overrides this?
            public_key_material=None,
        )
        ## Private key generated from the KeyPair:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ssm.StringParameter.html
        # TODO: Can't get these to work. Asked about it at:
        #       https://github.com/aws/aws-cdk/discussions/30049
        Tags.of(self.ssh_key_pair.private_key).add("SshKeyPairId", self.ssh_key_pair.key_pair_name)
        Tags.of(self.ssh_key_pair.private_key).add("Stack", construct_id)

        ########################
        ### SNS Notify STUFF ###
        ########################

        ## Create an SNS Topic for notifications:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_sns.Topic.html
        self.sns_notify_topic = sns.Topic(
            self,
            "SnsNotifyTopic",
            display_name=f"{construct_id}-sns-notify-topic",
        )
        # Give CloudWatch Alarms permissions to publish to the SNS Topic:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_sns.Topic.html#addwbrtowbrresourcewbrpolicystatement
        self.sns_notify_topic.add_to_resource_policy(
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_iam.PolicyStatement.html
            iam.PolicyStatement(
                actions=["sns:Publish"],
                effect=iam.Effect.ALLOW,
                resources=[self.sns_notify_topic.topic_arn],
                principals=[iam.ServicePrincipal("cloudwatch.amazonaws.com")],
                conditions={
                    "StringEquals": {
                        f"aws:ResourceTag/{application_id_tag_name}": application_id_tag_value,
                        "aws:ResourceAccount": self.account,
                    },
                },
            )
        )
        subscriptions = config.get("AlertSubscription", [])
        add_sns_subscriptions(self, self.sns_notify_topic, subscriptions)


        #####################
        ### Route53 STUFF ###
        #####################
        if "Domain" not in config:
            raise ValueError("Required key 'Domain' missing from config. See `./ContainerManager/README.md` on writing configs")
        if "Name" not in config["Domain"]:
            raise ValueError("Required key 'Domain.Name' missing from config. See `./ContainerManager/README.md` on writing configs")

        self.domain_name = str(config["Domain"]["Name"]).lower()
        self.root_hosted_zone_id = config["Domain"].get("HostedZoneId")

        if self.root_hosted_zone_id:
            ## Import the existing Route53 Hosted Zone:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_route53.PublicHostedZoneAttributes.html
            self.root_hosted_zone = route53.PublicHostedZone.from_hosted_zone_attributes(
                self,
                "RootHostedZone",
                hosted_zone_id=self.root_hosted_zone_id,
                zone_name=self.domain_name,
            )
        else:
            ## Create a Route53 Hosted Zone:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_route53.PublicHostedZone.html
            self.root_hosted_zone = route53.PublicHostedZone(
                self,
                "RootHostedZone",
                zone_name=self.domain_name,
                comment=f"Hosted zone for {construct_id}: {self.domain_name}",
            )
            self.root_hosted_zone.apply_removal_policy(RemovalPolicy.DESTROY)
