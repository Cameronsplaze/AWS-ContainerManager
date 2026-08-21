
"""
This adds the container info to DomainStack's hosted zone,
and starts the ASG when someone connects.

Needs to be in us-east-1, since it uses Route53 logs.
Needs to be deployed after ContainerManagerStack, since it references it.
"""

import json

from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
    RemovalPolicy,
    Validations,
    Acknowledgment,
    aws_iam as iam,
    aws_logs as logs,
    aws_logs_destinations as logs_destinations,
    aws_lambda as aws_lambda,
)
from constructs import Construct

from ContainerManager.leaf_stack_group.container_manager_stack import ContainerManagerStack
from ContainerManager.leaf_stack_group.domain_stack import DomainStack
from ContainerManager.leaf_stack_group.lambda_functions.lambda_powertools import PowertoolsFunction

class StartSystemStack(Stack):
    """
    This stacks sets up the lambda to turn the system on,
    and adds the DNS records to trigger it.
    """
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        domain_stack: DomainStack,
        container_manager_stack: ContainerManagerStack,
        container_id: str,
        config: dict,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        container_id_alpha = "".join(e for e in container_id.title() if e.isalnum())

        ## Log group for the lambda function:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_logs.LogGroup.html
        self.log_group_start_system = logs.LogGroup(
            self,
            "LogGroupStartSystem",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
            log_group_name=f"/aws/lambda/{container_id}-lambda-start-system",
        )

        ## Policy/Role for lambda function:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_iam.Role.html
        self.start_system_role = iam.Role(
            self,
            "StartSystemRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Role for the StartSystem lambda function.",
        )
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_iam.Policy.html
        self.start_system_policy = iam.Policy(
            self,
            "StartSystemPolicy",
            roles=[self.start_system_role],
            # Statements added at the end of this file:
            statements=[],
        )

        ## Lambda that turns system on
        # (PowertoolsFunction sets the runtime/handler, and adds the Powertools layer + env vars):
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_lambda.Function.html
        self.lambda_start_system = PowertoolsFunction(
            self,
            "StartSystem",
            description=f"{container_id_alpha}-lambda-start-system: Spin up ASG when someone connects.",
            code=aws_lambda.Code.from_asset("./ContainerManager/leaf_stack_group/lambda_functions/trigger_start_system/"),
            timeout=Duration.seconds(30),
            log_group=self.log_group_start_system,
            role=self.start_system_role,
            environment={
                "ASG_NAME": container_manager_stack.ecs_asg_nested_stack.auto_scaling_group.auto_scaling_group_name,
                "MANAGER_STACK_REGION": container_manager_stack.region,
                "ALLOWED_CIDR_IPS": json.dumps(list(set(config["Ec2"]["GameCidrAllowed"] + config["Ec2"]["SshCidrAllowed"]))),
                ## Metric info to let the system know someone is trying to connect, and don't spin down:
                "METRIC_NAMESPACE": container_manager_stack.watchdog_nested_stack.metric_namespace,
                "METRIC_NAME": container_manager_stack.watchdog_nested_stack.traffic_dns_metric.metric_name,
                "METRIC_THRESHOLD": str(container_manager_stack.watchdog_nested_stack.threshold),
                ## Convert METRIC_UNIT from an Enum, to a string that boto3 expects. (Words must have first
                #   letter capitalized too, which is what `.title()` does. Otherwise they'd be all caps).
                "METRIC_UNIT": container_manager_stack.watchdog_nested_stack.metric_unit.value.title(),
                "METRIC_DIMENSIONS": json.dumps(container_manager_stack.watchdog_nested_stack.metric_dimension_map),
            },
        )

        ## Trigger the system when someone connects:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_logs.SubscriptionFilter.html
        # https://conermurphy.com/blog/route53-hosted-zone-lambda-dns-invocation-aws-cdk
        self.subscription_filter = logs.SubscriptionFilter(
            self,
            "SubscriptionFilter",
            log_group=domain_stack.route53_query_log_group,
            destination=logs_destinations.LambdaDestination(self.lambda_start_system),
            # TODO: See if there's a way to put ec2_config.GameCidrAllowed/SshCidrAllowed in this, so it won't even spin up
            #    Might have to do it in the lambda itself, based on it's event.
            filter_pattern=logs.FilterPattern.any_term(domain_stack.dns_log_query_filter),
        )

        ### Add Lambda's permissions, now that you can reference everything:
        # Let lambda write to it's log group:
        self.log_group_start_system.grant_write(self.lambda_start_system)
        # Give it permissions to push to the metric:
        self.start_system_policy.add_statements(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["cloudwatch:PutMetricData"],
                resources=["*"],
                conditions={
                    "StringEquals": {
                        "cloudwatch:namespace": container_manager_stack.watchdog_nested_stack.metric_namespace,
                    }
                }
            )
        )
        # Give it permissions to update the ASG desired_capacity:
        self.start_system_policy.add_statements(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "autoscaling:UpdateAutoScalingGroup",
                ],
                resources=[container_manager_stack.ecs_asg_nested_stack.auto_scaling_group.auto_scaling_group_arn],
            )
        )

        ###############
        ### Outputs ###
        ###############
        # Because this is the very last stack, this output will show at the end of the terminal output:
        CfnOutput(self, "DomainName", value=domain_stack.sub_domain_name, description="[Domain]: The domain for the container.")
        # Also save it to the domain stack:
        CfnOutput(domain_stack, "DomainName", value=domain_stack.sub_domain_name, description="[Domain]: The domain for the container.")
        # Aaaand the main leaf stack too:
        CfnOutput(container_manager_stack, "DomainName", value=domain_stack.sub_domain_name, description="[Domain]: The domain for the container.")

        #####################
        ### cdk_nag stuff ###
        #####################
        # Do at very end, they have to "suppress" after everything's created to work.

        Validations.of(self.start_system_policy).acknowledge(
            Acknowledgment(
                id='AwsSolutions-IAM5[{"regex": "/^Resource::arn:aws:autoscaling:(.*):(.*):autoScalingGroup:\\*:autoScalingGroupName/(.*)$/g"}]',
                reason="It's flagging on the built-in auto-scaling arn. Nothing to do. (The '*' between autoScalingGroup and autoScalingGroupName.)",
                # apply_to_children=True,
            ),
        )
        Validations.of(self.start_system_policy).acknowledge(
            Acknowledgment(
                id='AwsSolutions-IAM5[{"appliesTo": ["Resource::*"]}]',
                reason="CloudWatch Metrics don't have ARN's. You need '*' to push to them. We lock down permissions based on Namespace.",
                # apply_to_children=True,
            ),
        )
