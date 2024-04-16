
import json

from aws_cdk import (
    Stack,
    Duration,
    aws_iam as iam,
    aws_logs as logs,
    aws_logs_destinations as logs_destinations,
    aws_lambda as aws_lambda,
)
from constructs import Construct

from ContainerManager.leaf_stack.main import ContainerManagerStack
from ContainerManager.leaf_stack.domain_info import DomainStack


class LinkTogetherStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, domain_stack: DomainStack, manager_stack: ContainerManagerStack, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        ## Lambda that turns system on
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_lambda.Function.html
        self.lambda_start_system = aws_lambda.Function(
            self,
            "lambda-start-system",
            description=f"{construct_id}-lambda-start-system: Turn system on, when someone connects.",
            code=aws_lambda.Code.from_asset("./lambda-start-system/"),
            handler="main.lambda_handler",
            runtime=aws_lambda.Runtime.PYTHON_3_12,
            timeout=Duration.seconds(30),
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "ASG_NAME": manager_stack.auto_scaling_group.auto_scaling_group_name,
                "MANAGER_STACK_REGION": manager_stack.region,
                ## Metric info to let the system know someone is trying to connect, and don't spin down:
                "METRIC_NAMESPACE": manager_stack.metric_namespace,
                "METRIC_NAME": manager_stack.metric_num_connections.metric_name,
                # Convert METRIC_UNIT from an Enum, to a string that boto3 expects. (Words must have first
                #   letter capitalized too, which is what `.title()` does. Otherwise they'd be all caps).
                "METRIC_UNIT": manager_stack.metric_unit.value.title(),
                "METRIC_DIMENSIONS": json.dumps(manager_stack.metric_dimension_map),

            },
        )
        # Give it permissions to update the ASG desired_capacity:
        self.lambda_start_system.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "autoscaling:UpdateAutoScalingGroup",
                ],
                resources=[manager_stack.auto_scaling_group.auto_scaling_group_arn],
            )
        )
        # Give it permissions to push to the metric:
        self.lambda_start_system.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["cloudwatch:PutMetricData"],
                resources=["*"],
                conditions={
                    "StringEquals": {
                        "cloudwatch:namespace": manager_stack.metric_namespace,
                    }
                }
            )
        )

        ## Trigger the system when someone connects:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_logs.SubscriptionFilter.html
        # https://conermurphy.com/blog/route53-hosted-zone-lambda-dns-invocation-aws-cdk
        self.subscription_filter = logs.SubscriptionFilter(
            self,
            "subscription-filter",
            log_group=domain_stack.route53_query_log_group,
            destination=logs_destinations.LambdaDestination(self.lambda_start_system),
            filter_pattern=logs.FilterPattern.any_term(domain_stack.sub_domain_name),
            filter_name="TriggerLambdaOnConnect",
        )