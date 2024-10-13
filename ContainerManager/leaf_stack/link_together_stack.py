
"""
This Links together the Main Stack, and Domain Stack.

Needed since they're in different regions, and we need
    to know about objects from both.
"""

import json

from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_iam as iam,
    aws_logs as logs,
    aws_logs_destinations as logs_destinations,
    aws_lambda as aws_lambda,
)
from constructs import Construct

from cdk_nag import NagSuppressions

from ContainerManager.leaf_stack.main import ContainerManagerStack
from ContainerManager.leaf_stack.domain_stack import DomainStack


class LinkTogetherStack(Stack):
    """
    This stacks sets up the lambda to turn the system on.
    """
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        domain_stack: DomainStack,
        manager_stack: ContainerManagerStack,
        container_id: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

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
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_lambda.Function.html
        self.lambda_start_system = aws_lambda.Function(
            self,
            "StartSystem",
            description=f"{container_id}-lambda-start-system: Spin up ASG when someone connects.",
            code=aws_lambda.Code.from_asset("./ContainerManager/leaf_stack/lambda/trigger-start-system/"),
            handler="main.lambda_handler",
            runtime=aws_lambda.Runtime.PYTHON_3_12,
            timeout=Duration.seconds(30),
            log_group=self.log_group_start_system,
            role=self.start_system_role,
            environment={
                "ASG_NAME": manager_stack.ecs_asg_nested_stack.auto_scaling_group.auto_scaling_group_name,
                "MANAGER_STACK_REGION": manager_stack.region,
                ## Metric info to let the system know someone is trying to connect, and don't spin down:
                "METRIC_NAMESPACE": manager_stack.watchdog_nested_stack.metric_namespace,
                "METRIC_NAME": manager_stack.watchdog_nested_stack.metric_activity_count.metric_name,
                "METRIC_THRESHOLD": str(manager_stack.watchdog_nested_stack.threshold),
                ## Convert METRIC_UNIT from an Enum, to a string that boto3 expects. (Words must have first
                #   letter capitalized too, which is what `.title()` does. Otherwise they'd be all caps).
                "METRIC_UNIT": manager_stack.watchdog_nested_stack.metric_unit.value.title(),
                "METRIC_DIMENSIONS": json.dumps(manager_stack.watchdog_nested_stack.metric_dimension_map),
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
            # Spaces on either side, so it doesn't match the "_tcp" query that pairs with it:
            filter_pattern=logs.FilterPattern.any_term(f" {domain_stack.sub_domain_name} "),
            filter_name="TriggerLambdaOnConnect",
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
                        "cloudwatch:namespace": manager_stack.watchdog_nested_stack.metric_namespace,
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
                resources=[manager_stack.ecs_asg_nested_stack.auto_scaling_group.auto_scaling_group_arn],
            )
        )

        #####################
        ### cdk_nag stuff ###
        #####################
        # Do at very end, they have to "suppress" after everything's created to work.

        NagSuppressions.add_resource_suppressions(
            self.start_system_policy,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "It's flagging on the built-in auto-scaling arn. Nothing to do. (The '*' between autoScalingGroup and autoScalingGroupName.)",
                    "appliesTo": [{"regex": "/^Resource::arn:aws:autoscaling:(.*):(.*):autoScalingGroup:\\*:autoScalingGroupName/(.*)$/g"}],
                },
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "CloudWatch Metrics don't have ARN's. You need '*' to push to them. We lock down permissions based on Namespace.",
                    "appliesTo": ["Resource::*"]
                }
            ],
            apply_to_children=True,
        )
