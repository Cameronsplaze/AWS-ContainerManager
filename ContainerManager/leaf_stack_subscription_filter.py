
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_route53 as route53,
    aws_iam as iam,
    aws_logs as logs,
    aws_logs_destinations as logs_destinations,
)
from constructs import Construct

from .leaf_stack_domain_info import DomainStack
from .leaf_stack_main import ContainerManagerStack

class SubscriptionFilterStack(Stack):
    """
    The whole point of this stack is to avoid a circular dependency.
        - Subscription filter HAS to be in the same region as the logs
            (And Route53 requires logs to be in us-east-1)
        - I want the MAIN stack with lambda to have the region configurable (us-west-2)
        - Because the configurable stack is deployed AFTER the domain stack, I have to
            deploy a third stack LAST so it can reference both stacks, and still be BACK in us-east-1
    """
    def __init__(self, scope: Construct, construct_id: str, domain_stack: DomainStack, manager_stack: ContainerManagerStack, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        ## Trigger the system when someone connects:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_logs.SubscriptionFilter.html
        self.subscription_filter = logs.SubscriptionFilter(
            self,
            f"{construct_id}-subscription-filter",
            log_group=domain_stack.route53_query_log_group,
            destination=logs_destinations.LambdaDestination(manager_stack.lambda_switch_system),
            filter_pattern=logs.FilterPattern.any_term(domain_stack.sub_domain_name),
            filter_name="TriggerLambdaOnConnect",
        )
