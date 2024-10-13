
"""
This module contains the AsgStateChangeHook NestedStack class.
"""

from aws_cdk import (
    NestedStack,
    Duration,
    RemovalPolicy,
    aws_lambda,
    aws_iam as iam,
    aws_logs as logs,
    aws_ecs as ecs,
    aws_events as events,
    aws_cloudwatch as cloudwatch,
    aws_events_targets as events_targets,
    aws_autoscaling as autoscaling,
)
from constructs import Construct

from cdk_nag import NagSuppressions

from ContainerManager.leaf_stack.domain_stack import DomainStack

class AsgStateChangeHook(NestedStack):
    """
    Contains the infrastructure to keep the management logic
    in sync with the ASG/Instance state.
    """
    def __init__(
        self,
        scope: Construct,
        container_id: str,
        domain_stack: DomainStack,
        ecs_cluster: ecs.Cluster,
        ec2_service: ecs.Ec2Service,
        auto_scaling_group: autoscaling.AutoScalingGroup,
        rule_watchdog_trigger: events.Rule,
        dashboard_widgets: list[tuple[int, cloudwatch.IWidget]],
        **kwargs,
    ) -> None:
        super().__init__(scope, "AsgStateChangeHook", **kwargs)

        ## Log group for the lambda function:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_logs.LogGroup.html
        self.log_group_asg_statechange_hook = logs.LogGroup(
            self,
            "LogGroupStartSystem",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
            log_group_name=f"/aws/lambda/{container_id}-asg-state-change-hook",
        )

        ## Policy/Role for lambda function:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_iam.Role.html
        self.asg_state_change_role = iam.Role(
            self,
            "AsgStateChangeHookRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Role for the AsgStateChangeHook lambda function.",
        )
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_iam.Policy.html
        self.asg_state_change_policy = iam.Policy(
            self,
            "AsgStateChangeHookPolicy",
            roles=[self.asg_state_change_role],
            # Statements added at the end of this file:
            statements=[],
        )

        ## Lambda function to update the DNS record:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_lambda.Function.html
        self.lambda_asg_state_change_hook = aws_lambda.Function(
            self,
            "AsgStateChangeHook",
            description=f"{container_id}-ASG-StateChange: Triggered by ec2 state changes. Starts/Stops the management logic",
            code=aws_lambda.Code.from_asset("./ContainerManager/leaf_stack/lambda/instance-StateChange-hook/"),
            handler="main.lambda_handler",
            runtime=aws_lambda.Runtime.PYTHON_3_12,
            timeout=Duration.seconds(30),
            log_group=self.log_group_asg_statechange_hook,
            role=self.asg_state_change_role,
            environment={
                "HOSTED_ZONE_ID": domain_stack.sub_hosted_zone.hosted_zone_id,
                "DOMAIN_NAME": domain_stack.sub_domain_name,
                "UNAVAILABLE_IP": domain_stack.unavailable_ip,
                "DNS_TTL": str(domain_stack.dns_ttl),
                "RECORD_TYPE": domain_stack.record_type.value,
                "WATCH_INSTANCE_RULE": rule_watchdog_trigger.rule_name,
                "ECS_CLUSTER_NAME": ecs_cluster.cluster_name,
                "ECS_SERVICE_NAME": ec2_service.service_name,
            },
        )
        ### Lambda Permissions:
        # Give it write to it's own log group:
        self.log_group_asg_statechange_hook.grant_write(self.lambda_asg_state_change_hook)
        # Give it permission to describe the stuff it needs to know about::
        self.asg_state_change_policy.add_statements(
            iam.PolicyStatement(
                # NOTE: these are on the list of actions that CANNOT be locked down
                #   in ANY way. You *must* use a wild card, and conditions *don't* work 🙄
                effect=iam.Effect.ALLOW,
                actions=[
                    # To get the IP of a new instance:
                    "ec2:DescribeInstances",
                    # To make sure no other instances are starting up:
                    "autoscaling:DescribeAutoScalingGroups",
                ],
                resources=["*"],
            )
        )
        # Give it permissions to update the service desired_task:
        self.asg_state_change_policy.add_statements(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ecs:UpdateService",
                    "ecs:DescribeServices",
                ],
                resources=[ec2_service.service_arn],
            )
        )
        ## Let it update the DNS record of this stack:
        self.asg_state_change_policy.add_statements(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["route53:ChangeResourceRecordSets"],
                resources=[domain_stack.sub_hosted_zone.hosted_zone_arn],
            )
        )
        ## Let it enable/disable the cron rule for counting connections:
        self.asg_state_change_policy.add_statements(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "events:EnableRule",
                    "events:DisableRule",
                ],
                resources=[rule_watchdog_trigger.rule_arn],
            )
        )

        ## EventBridge Rule: This is actually what hooks the Lambda to the ASG/Instance.
        #    Needed to keep the management in sync with if a container is running.
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events.Rule.html
        self.rule_asg_state_change_trigger = events.Rule(
            self,
            "AsgStateChangeTrigger",
            rule_name=f"{container_id}-rule-ASG-StateChange-hook",
            description="Trigger Lambda whenever the ASG state changes, to keep DNS in sync",
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events.EventPattern.html
            event_pattern=events.EventPattern(
                source=["aws.autoscaling"],
                # "EC2 Instance Launch Successful" -> FINISHES spinning up (has an ip now)
                # "EC2 Instance-terminate Lifecycle Action" -> STARTS to spin down (shorter
                #                          wait time than "EC2 Instance Terminate Successful").
                detail_type=["EC2 Instance Launch Successful", "EC2 Instance-terminate Lifecycle Action"],
                detail={
                    "AutoScalingGroupName": [auto_scaling_group.auto_scaling_group_name],
                },
            ),
            targets=[
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events_targets.LambdaFunction.html
                events_targets.LambdaFunction(self.lambda_asg_state_change_hook),
            ],
        )

        #######################
        ### Dashboard Stuff ###
        #######################
        ### Add asg_state_change_hook's invocations to the dashboard:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_lambda.Function.html#metricwbrinvocationsprops
        metric_state_change_invocations = self.lambda_asg_state_change_hook.metric_invocations()
        ## Graph it:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.GraphWidget.html
        widget_state_change_invocations = cloudwatch.GraphWidget(
            title="(Lambda) ASG State Change Invocations",
            # Only show up to an hour ago:
            start="-PT1H",
            height=6,
            width=12,
            right=[metric_state_change_invocations],
            legend_position=cloudwatch.LegendPosition.RIGHT,
            period=Duration.minutes(1),
            statistic="Sum",
        )
        dashboard_widgets.append((0, widget_state_change_invocations))

        #####################
        ### cdk_nag stuff ###
        #####################
        # Do at very end, they have to "suppress" after everything's created to work.

        NagSuppressions.add_resource_suppressions(
            self.asg_state_change_policy,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "These actions require the wildcard resource, since they're 'Describe'.",
                    "appliesTo": ["Resource::*"]
                }
            ],
            apply_to_children=True,
        )