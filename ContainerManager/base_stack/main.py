
"""
This module contains the BaseStackMain class.
"""

from constructs import Construct
from aws_cdk import (
    Stack,
    CfnOutput,
    aws_ec2 as ec2,
    aws_sns as sns,
    aws_iam as iam,
    aws_route53 as route53,
)

from cdk_nag import NagSuppressions

# from .utils.get_param import get_param
from ContainerManager.utils.sns_subscriptions import add_sns_subscriptions

class BaseStack(Stack):
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
            max_azs=config["Vpc"]["MaxAZs"],
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name=f"public-{construct_id}-sn",
                    subnet_type=ec2.SubnetType.PUBLIC,
                )
            ],
            restrict_default_security_group=True,
        )

        ## For enabling SSH access:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2.KeyPair.html
        self.ssh_key_pair = ec2.KeyPair(
            self,
            "SshKeyPair",
            public_key_material=None,
            key_pair_name=f"{construct_id}-SshKey",
        )

        ########################
        ### SNS Notify STUFF ###
        ########################

        ## Create an SNS Topic for notifications:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_sns.Topic.html
        self.sns_notify_topic = sns.Topic(
            self,
            "SnsNotifyTopic",
            display_name=f"{construct_id}-sns-notify-topic",
            enforce_ssl=True,
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
        add_sns_subscriptions(self, self.sns_notify_topic, config["AlertSubscription"])

        #####################
        ### Route53 STUFF ###
        #####################
        # domain_name is imported to other stacks, so save it to this one:
        self.domain_name = config["Domain"]["Name"]

        ## Import the existing Route53 Hosted Zone:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_route53.PublicHostedZoneAttributes.html
        self.root_hosted_zone = route53.PublicHostedZone.from_hosted_zone_attributes(
            self,
            "RootHostedZone",
            hosted_zone_id=config["Domain"]["HostedZoneId"],
            zone_name=self.domain_name,
        )

        ####################
        ### Output Stuff ###
        ####################
        CfnOutput(self, "SshKeyPairId", value=f"/ec2/keypair/{self.ssh_key_pair.key_pair_id}")
        CfnOutput(self, "HostedZoneId", value=config["Domain"]["HostedZoneId"])

        #####################
        ### Export Values ###
        #####################
        ## To stop cdk from trying to delete the exports when cdk is deployed by
        ## itself, but still has leaf stacks attached to it.
        # https://blogs.thedevs.co/aws-cdk-export-cannot-be-deleted-as-it-is-in-use-by-stack-5c205b8004b4
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.ExportValueOptions.html
        # https://github.com/aws/aws-cdk/blob/v1-main/packages/@aws-cdk/core/README.md#removing-automatic-cross-stack-references
        self.export_value(self.ssh_key_pair.key_pair_name)
        self.export_value(self.sns_notify_topic.topic_arn)
        self.export_value(self.vpc.vpc_id)
        for subnet in self.vpc.public_subnets:
            self.export_value(subnet.subnet_id)

        #####################
        ### cdk_nag stuff ###
        #####################
        # Do at very end, they have to "suppress" after everything's created to work.
        NagSuppressions.add_resource_suppressions(self.sns_notify_topic, [
            {
                "id": "AwsSolutions-SNS2",
                "reason": "KMS is costing ~3/month, and this isn't sensitive data anyways.",
            },
        ])

        NagSuppressions.add_resource_suppressions(
            self.vpc,
            [
                {
                    "id": "AwsSolutions-VPC7",
                    "reason": "Flow logs cost a lot, and the average user won't need them.",
                },
            ],
        )
