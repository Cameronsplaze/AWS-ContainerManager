
"""
This adds the container info to BaseStackDomain's hosted zone,
and starts the ASG when someone connects.

Needs to be in us-east-1, since it uses Route53 logs.
"""

import json

from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_route53 as route53,
    aws_iam as iam,
    aws_ssm as ssm,
    aws_logs as logs,
    aws_logs_destinations as logs_destinations,
    aws_lambda as aws_lambda,
)
from constructs import Construct

from cdk_nag import NagSuppressions

from ContainerManager.leaf_stack.main import ContainerManagerStack
from ContainerManager.base_stack import BaseStackDomain

class LeafStackStartSystem(Stack):
    """
    This stacks sets up the lambda to turn the system on,
    and adds the DNS records to trigger it.
    """
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        base_stack_domain: BaseStackDomain,
        leaf_stack_manager: ContainerManagerStack,
        container_id: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        container_id_alpha = "".join(e for e in container_id.title() if e.isalpha())
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ssm.StringParameter.html#static-fromwbrstringwbrparameterwbrattributesscope-id-attrs
        asg_name = ssm.StringParameter.from_string_parameter_attributes(
            self,
            "Import-AsgName",
            parameter_name=f"/{leaf_stack_manager.stack_name}/AsgName",
            simple_name=False,
        )
        asg_arn = ssm.StringParameter.from_string_parameter_attributes(
            self,
            "Import-AsgArn",
            parameter_name=f"/{leaf_stack_manager.stack_name}/AsgArn",
            simple_name=False,
        )

        ### Create the DNS record to trigger the lambda:
        # (Nothing actually referenced it directly)
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_route53.RecordSet.html
        self.dns_record = route53.RecordSet(
            self,
            "DnsRecord",
            zone=base_stack_domain.hosted_zone,
            record_name=leaf_stack_manager.container_url,
            record_type=base_stack_domain.record_type,
            target=route53.RecordTarget.from_values(base_stack_domain.unavailable_ip),
            ttl=Duration.seconds(base_stack_domain.dns_ttl),
        )
        self.dns_record.apply_removal_policy(RemovalPolicy.DESTROY)

        ## And if you have a imported hosted zone, add NS to link the two zones:
        ## Tie the two hosted zones together:
        if base_stack_domain.imported_hosted_zone_id:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_route53.HostedZone.html#static-fromwbrhostedwbrzonewbrattributesscope-id-attrs
            imported_hosted_zone = route53.HostedZone.from_hosted_zone_attributes(
                self,
                "ImportHostedZone",
                zone_name=base_stack_domain.domain_name,
                hosted_zone_id=base_stack_domain.imported_hosted_zone_id,
            )
            ## Point the imported zone to the hosted zone we can have query logs in:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_route53.NsRecord.html
            self.ns_record = route53.NsRecord(
                self,
                "NsRecord",
                zone=imported_hosted_zone,
                values=base_stack_domain.hosted_zone.hosted_zone_name_servers,
                record_name=leaf_stack_manager.container_url,
            )
            self.ns_record.apply_removal_policy(RemovalPolicy.DESTROY)

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
            description=f"{container_id_alpha}-lambda-start-system: Spin up ASG when someone connects.",
            code=aws_lambda.Code.from_asset("./ContainerManager/leaf_stack/lambda/trigger-start-system/"),
            handler="main.lambda_handler",
            runtime=aws_lambda.Runtime.PYTHON_3_12,
            timeout=Duration.seconds(30),
            log_group=self.log_group_start_system,
            role=self.start_system_role,
            environment={
                "ASG_NAME": asg_name.string_value,
                "MANAGER_STACK_REGION": leaf_stack_manager.region,
                ## Metric info to let the system know someone is trying to connect, and don't spin down:
                "METRIC_NAMESPACE": leaf_stack_manager.watchdog_nested_stack.metric_namespace,
                "METRIC_NAME": leaf_stack_manager.watchdog_nested_stack.traffic_dns_metric.metric_name,
                "METRIC_THRESHOLD": str(leaf_stack_manager.watchdog_nested_stack.threshold),
                ## Convert METRIC_UNIT from an Enum, to a string that boto3 expects. (Words must have first
                #   letter capitalized too, which is what `.title()` does. Otherwise they'd be all caps).
                "METRIC_UNIT": leaf_stack_manager.watchdog_nested_stack.metric_unit.value.title(),
                "METRIC_DIMENSIONS": json.dumps(leaf_stack_manager.watchdog_nested_stack.metric_dimension_map),
            },
        )


        ## Trigger the system when someone connects:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_logs.SubscriptionFilter.html
        # https://conermurphy.com/blog/route53-hosted-zone-lambda-dns-invocation-aws-cdk
        self.subscription_filter = logs.SubscriptionFilter(
            self,
            "SubscriptionFilter",
            log_group=base_stack_domain.route53_query_log_group,
            destination=logs_destinations.LambdaDestination(self.lambda_start_system),
            # Spaces on either side, so it doesn't match the "_tcp" query that pairs with it:
            filter_pattern=logs.FilterPattern.any_term(leaf_stack_manager.dns_log_query_filter),
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
                        "cloudwatch:namespace": leaf_stack_manager.watchdog_nested_stack.metric_namespace,
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
                resources=[asg_arn.string_value],
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
