

from aws_cdk import (
    NestedStack,
    Duration,
    aws_lambda,
    aws_iam as iam,
    aws_logs as logs,
    aws_ecs as ecs,
    aws_events as events,
    aws_events_targets as events_targets,
    aws_autoscaling as autoscaling,
)
from constructs import Construct

from ContainerManager.leaf_stack.domain_stack import DomainStack

class AsgStateChangeHook(NestedStack):
    def __init__(
        self,
        scope: Construct,
        leaf_construct_id: str,
        container_name_id: str,
        domain_stack: DomainStack,
        ecs_cluster: ecs.Cluster,
        ec2_service: ecs.Ec2Service,
        auto_scaling_group: autoscaling.AutoScalingGroup,
        rule_watchdog_trigger: events.Rule,
        **kwargs,
    ) -> None:
        super().__init__(scope, "AsgStateChangeHook", **kwargs)


        ## Lambda function to update the DNS record:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_lambda.Function.html
        self.lambda_asg_state_change_hook = aws_lambda.Function(
            self,
            "AsgStateChangeHook",
            description=f"{container_name_id}-ASG-StateChange: Triggered by ec2 state changes. Starts/Stops the management logic",
            code=aws_lambda.Code.from_asset("./ContainerManager/leaf_stack/lambda/instance-StateChange-hook/"),
            handler="main.lambda_handler",
            runtime=aws_lambda.Runtime.PYTHON_3_12,
            timeout=Duration.seconds(30),
            log_retention=logs.RetentionDays.ONE_WEEK,
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
        self.lambda_asg_state_change_hook.add_to_role_policy(
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
        self.lambda_asg_state_change_hook.add_to_role_policy(
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
        self.lambda_asg_state_change_hook.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["route53:ChangeResourceRecordSets"],
                resources=[domain_stack.sub_hosted_zone.hosted_zone_arn],
            )
        )
        ## Let it enable/disable the cron rule for counting connections:
        self.lambda_asg_state_change_hook.add_to_role_policy(
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
            rule_name=f"{container_name_id}-rule-ASG-StateChange-hook",
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
