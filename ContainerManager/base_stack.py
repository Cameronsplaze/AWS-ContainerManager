
"""
This module contains the ContainerManagerBaseStack class.
"""

from constructs import Construct
from aws_cdk import (
    Stack,
    Tags,
    Duration,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_route53 as route53,
    aws_sns as sns,
    aws_iam as iam,
    aws_cloudwatch as cloudwatch,
)

from cdk_nag import NagSuppressions

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

        ### Fact-check the maturity, and save it for leaf stacks:
        # (Makefile defaults to prod if not set. We want to fail-fast
        # here, so throw if it doesn't exist)
        self.maturity = self.node.get_context("maturity")
        supported_maturities = ["devel", "prod"]
        assert self.maturity in supported_maturities, f"ERROR: Unknown maturity. Must be in {supported_maturities}"

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
        self.root_hosted_zone_id = config["Domain"].get("HostedZoneId")

        if config["Domain"]["HostedZoneId"]:
            ## Import the existing Route53 Hosted Zone:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_route53.PublicHostedZoneAttributes.html
            self.root_hosted_zone = route53.PublicHostedZone.from_hosted_zone_attributes(
                self,
                "RootHostedZone",
                hosted_zone_id=config["Domain"]["HostedZoneId"],
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

        #######################
        ### Dashboard stuff ###
        #######################
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Dashboard.html
        self.dashboard = cloudwatch.Dashboard(
            self,
            "CloudwatchDashboard",
            dashboard_name=f"{construct_id}-dashboard",
            period_override=cloudwatch.PeriodOverride.AUTO,
        )
        ### There's a bug rn where you can't create blank widgets,
        # So TMP create a blank metric to attach to them:
        # BUG: https://github.com/aws/aws-cdk/issues/31393
        # DOCS: https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Metric.html
        blank_metric = cloudwatch.Metric(
            metric_name="blank",
            namespace="blank",
            period=Duration.minutes(1),
            statistic="Maximum",
        )

        # "Namespace" the widgets. All the leaf stacks will need to access them, but
        #    I don't want to have a ton of widgets directly in "self". Plus now we can
        #    loop over the dict to add to the dashboard instead of adding each one manually.
        self.dashboard_widgets = {
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.GraphWidget.html
            "AutoScalingGroup-Traffic": cloudwatch.GraphWidget(
                height=6,
                width=12,
                left=[blank_metric],
            ),
        }
        # Add the widgets to the dashboard:
        for widget in self.dashboard_widgets.values():
            self.dashboard.add_widgets(widget)


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