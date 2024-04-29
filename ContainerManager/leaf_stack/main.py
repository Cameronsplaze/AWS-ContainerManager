
import json
import re

from aws_cdk import (
    Stack,
    Duration,
    aws_lambda,
    aws_iam as iam,
    aws_logs as logs,
    aws_autoscaling as autoscaling,
    aws_events as events,
    aws_events_targets as targets,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cloudwatch_actions,
    aws_sns as sns,
)
from constructs import Construct

from ContainerManager.base_stack import ContainerManagerBaseStack
from ContainerManager.leaf_stack.domain_info import DomainStack
# from ContainerManager.utils.get_param import get_param
from ContainerManager.utils.sns_subscriptions import add_sns_subscriptions

## Import Nested Stacks:
from ContainerManager.leaf_stack import NestedStacks


class ContainerManagerStack(Stack):

    ## This makes the stack names of NestedStacks MUCH more readable:
    # (From: https://github.com/aws/aws-cdk/issues/18053 and https://github.com/aws/aws-cdk/issues/19099)
    def get_logical_id(self, element):
        if "NestedStackResource" in element.node.id:
            match = re.search(r'([a-zA-Z0-9]+)\.NestedStackResource', element.node.id)
            if match:
                # Returns "EfsNestedStack" instead of "EfsNestedStackEfsNestedStackResource..."
                return match.group(1)
            else:
                # Fail fast. If the logical_id ever changes on a existing stack, you replace everything and might loose data.
                raise RuntimeError(f"Could not find 'NestedStackResource' in {element.node.id}. Did a CDK update finally fix NestedStack names?")
        return super().get_logical_id(element)

    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            base_stack: ContainerManagerBaseStack,
            domain_stack: DomainStack,
            container_name_id: str,
            config: dict,
            **kwargs
        ) -> None:
        super().__init__(scope, construct_id, **kwargs)


        ###########
        ## Container-specific Notify
        ###########
        ## You can subscribe to this instead if you only care about one of
        ## the containers, and not every.

        ## Create an SNS Topic for notifications:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_sns.Topic.html
        self.sns_notify_topic = sns.Topic(
            self,
            "sns-notify-topic",
            display_name=f"{construct_id}-sns-notify-topic",
        )
        subscriptions = config.get("AlertSubscription", [])
        add_sns_subscriptions(self, self.sns_notify_topic, subscriptions)



        ### All the info for the Security Group Stuff
        sg_nested_stack = NestedStacks.SecurityGroups(
            self,
            construct_id,
            description=f"Security Group Logic for {construct_id}",
            vpc=base_stack.vpc,
            sg_vpc_traffic=base_stack.sg_vpc_traffic,
            docker_ports_config=config["Container"].get("Ports", []),
        )
        self.sg_efs_traffic = sg_nested_stack.sg_efs_traffic
        self.sg_container_traffic = sg_nested_stack.sg_container_traffic

        ### All the info for the Container Stuff
        container_nested_stack = NestedStacks.Container(
            self,
            construct_id,
            description=f"Container Logic for {construct_id}",
            container_name_id=container_name_id,
            docker_image=config["Container"]["Image"],
            docker_environment=config["Container"].get("Environment", {}),
            docker_ports_config=config["Container"].get("Ports", []),
            # sg_container_traffic=self.sg_container_traffic,
        )
        self.container = container_nested_stack.container
        self.task_definition = container_nested_stack.task_definition

        ### All the info for EFS Stuff
        efs_nested_stack = NestedStacks.Efs(
            self,
            construct_id,
            description=f"EFS Logic for {construct_id}",
            vpc=base_stack.vpc,
            task_definition=self.task_definition,
            container=self.container,
            volumes_config=config["Container"].get("Volumes", []),
            sg_efs_traffic=self.sg_efs_traffic,
        )
        self.efs_file_system = efs_nested_stack.efs_file_system
        self.host_access_point = efs_nested_stack.host_access_point

        ### All the info for the ECS and ASG Stuff
        ecs_asg_nested_stack = NestedStacks.EcsAsg(
            self,
            construct_id,
            description=f"Ec2Service Logic for {construct_id}",
            vpc=base_stack.vpc,
            task_definition=self.task_definition,
            instance_type=config["InstanceType"],
            sg_container_traffic=self.sg_container_traffic,
            ssh_key_pair=base_stack.ssh_key_pair,
            base_stack_sns_topic=base_stack.sns_notify_topic,
            leaf_stack_sns_topic=self.sns_notify_topic,
            efs_file_system=self.efs_file_system,
            host_access_point=self.host_access_point,
        )
        self.ecs_cluster = ecs_asg_nested_stack.ecs_cluster
        self.ec2_service = ecs_asg_nested_stack.ec2_service
        self.auto_scaling_group = ecs_asg_nested_stack.auto_scaling_group











        ## Scale down ASG if this is ever triggered:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_autoscaling.StepScalingAction.html
        # https://medium.com/swlh/deploy-your-auto-scaling-stack-with-aws-cdk-abae64f8e6b6
        #    TODO: Eventually BOTH of the lambdas will trigger this if they error:
        #       - (It's small enough, maybe just duplicate in each of the Nested Stacks?)
        #       - (Maybe move it to EcsAsg stack, since it uses the ASG????? I like this the most so far...)
        scale_down_asg_action = autoscaling.StepScalingAction(self,
            "scale-down-asg-action",
            auto_scaling_group=self.auto_scaling_group,
            adjustment_type=autoscaling.AdjustmentType.EXACT_CAPACITY,
        )
        scale_down_asg_action.add_adjustment(adjustment=0, lower_bound=0)










        ###########
        ## Setup Lambda WatchDog Timer
        ###########
        self.metric_namespace = construct_id
        self.metric_unit = cloudwatch.Unit.COUNT
        self.metric_dimension_map = {
            "ContainerNameID": container_name_id,
        }
        ## Custom Metric for the number of connections
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Metric.html
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/cloudwatch/client/put_metric_data.html
        self.metric_num_connections = cloudwatch.Metric(
            namespace=self.metric_namespace,
            metric_name="Metric-NumConnections",
            dimensions_map=self.metric_dimension_map,
            label="Number of Connections",
            unit=self.metric_unit,
            # If multiple requests happen in a period, this takes the higher of the two.
            # This way BOTH have to be zero for it to count as an alarm trigger.
            # (And it's still accurate, multiple of the same value will just be that value)
            statistic=cloudwatch.Stats.MAXIMUM,
            # It costs $0.30 to create this metric, but then the first million API
            # requests are free. Since this only happens when the container is up, we're fine.
            period=Duration.minutes(1),
        )
        ## Trigger if 0 people are connected for too long:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Metric.html#createwbralarmscope-id-props
        # Total Duration = Number of Periods * Period length... so
        # Number of Periods = Total Duration / Period length
        evaluation_periods = int(config.get("MinutesWithoutPlayers", 5) / self.metric_num_connections.period.to_minutes())
        self.alarm_num_connections = self.metric_num_connections.create_alarm(
            self,
            "Alarm-NumConnections",
            alarm_name=f"{construct_id}-Alarm-NumConnections",
            alarm_description="Trigger if 0 people are connected for too long",
            evaluation_periods=evaluation_periods,
            threshold=0,
            comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.MISSING,
        )
        ## Call this if switching to ALARM:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Alarm.html#addwbralarmwbractionactions
        self.alarm_num_connections.add_alarm_action(
            cloudwatch_actions.AutoScalingAction(scale_down_asg_action)
        )

        ## Lambda, count the number of connections and pass to CloudWatch Alarm
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_lambda.Function.html
        self.lambda_watchdog_num_connections = aws_lambda.Function(
            self,
            "lambda-watchdog-num-connections",
            description=f"{container_name_id}-Watchdog: Counts the number of connections to the container, and passes it to a CloudWatch Alarm.",
            code=aws_lambda.Code.from_asset("./ContainerManager/leaf_stack/lambda/watchdog-num-connections/"),
            handler="main.lambda_handler",
            runtime=aws_lambda.Runtime.PYTHON_3_12,
            timeout=Duration.seconds(30),
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "ASG_NAME": self.auto_scaling_group.auto_scaling_group_name,
                "TASK_DEFINITION": self.task_definition.family,
                "METRIC_NAMESPACE": self.metric_namespace,
                "METRIC_NAME": self.metric_num_connections.metric_name,
                # Convert from an Enum, to a string that boto3 expects. (Words must have first letter
                #   capitalized too, which is what `.title()` does. Otherwise they'd be all caps).
                "METRIC_UNIT": self.metric_unit.value.title(),
                "METRIC_DIMENSIONS": json.dumps(self.metric_dimension_map),
            },
        )
        # Just like the other lambda, check and find the running instance:
        self.lambda_watchdog_num_connections.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["autoscaling:DescribeAutoScalingGroups"],
                resources=["*"],
            )
        )
        # Give it permissions to send commands to the instance host:
        self.lambda_watchdog_num_connections.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ssm:SendCommand"],
                # No clue what the instance ID will be, so lock it to the ASG:
                resources=["*"],
                conditions={
                    "StringEquals": {
                        "aws:ResourceTag/aws:autoscaling:groupName": self.auto_scaling_group.auto_scaling_group_name,
                    }
                },
            )
        )
        self.lambda_watchdog_num_connections.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ssm:SendCommand"],
                resources=[f"arn:aws:ssm:{self.region}::document/AWS-RunShellScript"],
            )
        )
        self.lambda_watchdog_num_connections.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ssm:GetCommandInvocation"],
                resources=[f"arn:aws:ssm:{self.region}:{self.account}:*"],
            )
        )
        # Give it permissions to push metric data:
        self.lambda_watchdog_num_connections.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["cloudwatch:PutMetricData"],
                resources=["*"],
                conditions={
                    "StringEquals": {
                        "cloudwatch:namespace": self.metric_namespace,
                    }
                }
            )
        )

        ## Grab existing metric for Lambda fail alarm
        # https://bobbyhadz.com/blog/cloudwatch-alarm-aws-cdk
        ## Something like this:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_lambda.Function.html#metricwbrerrorsprops
        self.metric_watchdog_errors = self.lambda_watchdog_num_connections.metric_errors(
            label="Number of Watchdog Errors",
            unit=cloudwatch.Unit.COUNT,
            # If multiple requests happen in a period, and one isn't an error,
            # use that one.
            statistic=cloudwatch.Stats.MINIMUM,
            period=Duration.minutes(1),
        )
        self.alarm_watchdog_errors = self.metric_watchdog_errors.create_alarm(
            self,
            "Alarm-Watchdog-Errors",
            alarm_name=f"{construct_id}-Alarm-Watchdog-Errors",
            alarm_description="Trigger if the Lambda Watchdog fails too many times",
            # Must be in alarm this long consecutively to trigger. 3 strikes you're out:
            #      (Duration doesn't matter here, no need to divide by metric period. We ALWAYS want 3)
            evaluation_periods=3,
            # What counts as an alarm (ANY error here):
            threshold=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.MISSING,
        )

        ## Call this if switching to ALARM:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Alarm.html#addwbralarmwbractionactions
        self.alarm_watchdog_errors.add_alarm_action(
            cloudwatch_actions.AutoScalingAction(scale_down_asg_action)
        )

        ## EventBridge Rule to trigger lambda every minute, to see how many are using the container
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events.Rule.html
        self.rule_watchdog_trigger = events.Rule(
            self,
            "rule-watchdog-trigger",
            rule_name=f"{container_name_id}-rule-watchdog-trigger",
            description="Trigger Watchdog Lambda every minute, to see how many are using the container",
            schedule=events.Schedule.rate(Duration.minutes(1)),
            targets=[
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events_targets.LambdaFunction.html
                targets.LambdaFunction(self.lambda_watchdog_num_connections),
            ],
            # Start disabled, self.lambda_watchdog_num_connections will enable it when instance starts up 
            enabled=False,
        )




















        ## Lambda function to update the DNS record:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_lambda.Function.html
        self.lambda_asg_state_change_hook = aws_lambda.Function(
            self,
            "lambda-asg-StateChange-hook",
            description=f"{container_name_id}-ASG-StateChange: Triggered by ec2 state changes. Starts the management logic",
            code=aws_lambda.Code.from_asset("./ContainerManager/leaf_stack/lambda/instance-StateChange-hook/"),
            handler="main.lambda_handler",
            runtime=aws_lambda.Runtime.PYTHON_3_12,
            timeout=Duration.seconds(30),
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "HOSTED_ZONE_ID": domain_stack.sub_hosted_zone.hosted_zone_id,
                "DOMAIN_NAME": domain_stack.sub_domain_name,
                "UNAVAILABLE_IP": domain_stack.unavailable_ip,
                "UNAVAILABLE_TTL": str(domain_stack.unavailable_ttl),
                "RECORD_TYPE": domain_stack.record_type.value,
                "WATCH_INSTANCE_RULE": self.rule_watchdog_trigger.rule_name,
                "ECS_CLUSTER_NAME": self.ecs_cluster.cluster_name,
                "ECS_SERVICE_NAME": self.ec2_service.service_name,
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
                resources=[self.ec2_service.service_arn],
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
                resources=[self.rule_watchdog_trigger.rule_arn],
            )
        )

        ## EventBridge Rule: This is actually what hooks the Lambda to the ASG/Instance.
        #    Needed to keep the management in sync with if a container is running.
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events.Rule.html
        self.rule_asg_state_change_trigger = events.Rule(
            self,
            "rule-ASG-StateChange-hook",
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
                    "AutoScalingGroupName": [self.auto_scaling_group.auto_scaling_group_name],
                },
            ),
            targets=[
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events_targets.LambdaFunction.html
                targets.LambdaFunction(self.lambda_asg_state_change_hook),
            ],
        )

















        ## TODO: Think about moving these two into the EcsAsg stack instead maybe?
        ##       idk yet if it's worth creating a stack for just these two. Mayyybe.
        ##       You need to create the sns first in the beginning anyway, so everything
        ##       can push to it.

        ## EventBridge Rule: Send notification to user when ECS Task spins up or down:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events.Rule.html
        message = events.RuleTargetInput.from_text("\n".join([
            f"Container for '{container_name_id}' has started!",
            f"Connect to it at: '{domain_stack.sub_domain_name}'.",
        ]))
        self.rule_notify_up = events.Rule(
            self,
            "rule-notify-up",
            rule_name=f"{container_name_id}-rule-notify-up",
            description="Let user know when system finishes spinning UP",
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events.EventPattern.html
            event_pattern=events.EventPattern(
                source=["aws.ecs"],
                detail_type=["ECS Task State Change"],
                detail={
                    "clusterArn": [self.ecs_cluster.cluster_arn],
                    # You only care if the TASK starts, or the INSTANCE stops:
                    "lastStatus": ["RUNNING"],
                    "desiredStatus": ["RUNNING"],
                },
            ),
            targets=[
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events_targets.SnsTopic.html
                targets.SnsTopic(
                    base_stack.sns_notify_topic,
                    message=message,
                ),
                targets.SnsTopic(
                    self.sns_notify_topic,
                    message=message,
                ),
            ],
        )

        ## Same thing, but notify user when task spins down finally:
        ##   (Can't combine with above target, since we care about different 'detail_type'.
        ##    Don't want to spam the user sadly.)
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events.Rule.html
        message = events.RuleTargetInput.from_text(f"Container for '{container_name_id}' has stopped.")
        self.rule_notify_down = events.Rule(
            self,
            "rule-notify-down",
            rule_name=f"{container_name_id}-rule-notify-up-down",
            description="Let user know when system finishes spinning down",
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events.EventPattern.html
            event_pattern=events.EventPattern(
                source=["aws.autoscaling"],
                detail_type=["EC2 Instance-terminate Lifecycle Action"],
                detail={
                    "AutoScalingGroupName": [self.auto_scaling_group.auto_scaling_group_name],
                },
            ),
            targets=[
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events_targets.SnsTopic.html
                targets.SnsTopic(base_stack.sns_notify_topic, message=message),
                targets.SnsTopic(self.sns_notify_topic, message=message),
            ],
        )

