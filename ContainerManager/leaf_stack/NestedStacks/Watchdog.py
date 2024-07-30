
import json

from aws_cdk import (
    NestedStack,
    Duration,
    aws_lambda,
    aws_iam as iam,
    aws_ecs as ecs,
    aws_logs as logs,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cloudwatch_actions,
    aws_autoscaling as autoscaling,
    aws_events as events,
    aws_events_targets as events_targets,
)
from constructs import Construct

class Watchdog(NestedStack):
    def __init__(
        self,
        scope: Construct,
        leaf_construct_id: str,
        container_id: str,
        watchdog_config: dict,
        task_definition: ecs.Ec2TaskDefinition,
        auto_scaling_group: autoscaling.AutoScalingGroup,
        scale_down_asg_action: autoscaling.StepScalingAction,
        **kwargs,
    ) -> None:
        super().__init__(scope, "WatchdogNestedStack", **kwargs)

        self.metric_namespace = leaf_construct_id
        self.metric_unit = cloudwatch.Unit.COUNT
        self.metric_dimension_map = {
            "ContainerNameID": container_id,
        }
        ## Custom Metric for the number of connections
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Metric.html
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/cloudwatch/client/put_metric_data.html
        if watchdog_config["Type"] == "TCP":
            label = "Number of Connections"
        elif watchdog_config["Type"] == "UDP":
            label = f"Number of packets in since last check"
        self.metric_activity_count = cloudwatch.Metric(
            metric_name=f"Metric-ContainerActivity-{watchdog_config['Type']}",
            namespace=self.metric_namespace,
            dimensions_map=self.metric_dimension_map,
            label=label,
            unit=self.metric_unit,
            # If multiple requests happen in a period, this takes the higher of the two.
            # This way BOTH have to be zero for it to count as an alarm trigger.
            # (And it's still accurate, multiple of the same value will just be that value)
            statistic=cloudwatch.Stats.MAXIMUM,
            # It costs $0.30 to create this metric, but then the first million API
            # requests are free. Since this only happens when the container is up, we're fine.
            period=Duration.minutes(1),
        )

        self.metric_ssh_connections = cloudwatch.Metric(
            metric_name=f"Metric-SSH-Connections",
            namespace=self.metric_namespace,
            dimensions_map=self.metric_dimension_map,
            label="Number of SSH Connections",
            unit=self.metric_unit,
            statistic=cloudwatch.Stats.MAXIMUM,
            period=Duration.minutes(1),
        )

        ## Combine two metrics here before creating the alarm:
        # Docs: https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.MathExpression.html
        # Info: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/using-metric-math.html
        ## (Save threshold, it's also used in dns stack to NOT trip alarm if someone is connecting)
        self.threshold = watchdog_config["Threshold"]
        self.metric_total_activity = cloudwatch.MathExpression(
            expression=f"ssh > 0 OR activity > {self.threshold}",
            using_metrics={
                "ssh": self.metric_ssh_connections,
                "activity": self.metric_activity_count,
            },
            label="(Bool) total container activity",
            period=Duration.minutes(1),
        )

        ## Trigger if 0 people are connected for too long:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Metric.html#createwbralarmscope-id-props
        #       Total Duration = Number of Periods * Period length... so
        #       Number of Periods = Total Duration / Period length
        evaluation_periods = int(watchdog_config["MinutesWithoutConnections"] / self.metric_total_activity.period.to_minutes())
        self.alarm_container_activity = self.metric_total_activity.create_alarm(
            self,
            "AlarmContainerActivity",
            alarm_name=f"{leaf_construct_id}-Alarm-ContainerActivity",
            alarm_description="Trigger if 0 people are connected for too long",
            evaluation_periods=evaluation_periods,
            threshold=0,
            comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.MISSING,
        )
        ## Call this if switching to ALARM:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Alarm.html#addwbralarmwbractionactions
        self.alarm_container_activity.add_alarm_action(
            cloudwatch_actions.AutoScalingAction(scale_down_asg_action)
        )

        ## Lambda, count the number of connections and pass to CloudWatch Alarm
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_lambda.Function.html
        self.lambda_watchdog_container_activity = aws_lambda.Function(
            self,
            "WatchdogContainerActivity",
            description=f"{container_id}-Watchdog: Counts the number of connections to the container, and passes it to a CloudWatch Alarm.",
            code=aws_lambda.Code.from_asset("./ContainerManager/leaf_stack/lambda/watchdog-container-activity/"),
            handler="main.lambda_handler",
            runtime=aws_lambda.Runtime.PYTHON_3_12,
            timeout=Duration.seconds(30),
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "ASG_NAME": auto_scaling_group.auto_scaling_group_name,
                "TASK_DEFINITION": task_definition.family,
                "METRIC_NAMESPACE": self.metric_namespace,
                "METRIC_NAME_ACTIVITY_COUNT": self.metric_activity_count.metric_name,
                "METRIC_NAME_SSH_CONNECTIONS": self.metric_ssh_connections.metric_name,
                # Convert from an Enum, to a string that boto3 expects. (Words must have first letter
                #   capitalized too, which is what `.title()` does. Otherwise they'd be all caps).
                "METRIC_UNIT": self.metric_unit.value.title(),
                "METRIC_DIMENSIONS": json.dumps(self.metric_dimension_map),
                # Load the config options, depending on connection type:
                "CONNECTION_TYPE": watchdog_config["Type"],
                "TCP_PORT": str(watchdog_config.get("TcpPort", "")),
            },
        )
        # Just like the other lambda, check and find the running instance:
        self.lambda_watchdog_container_activity.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["autoscaling:DescribeAutoScalingGroups"],
                resources=["*"],
            )
        )
        # Give it permissions to send commands to the instance host:
        self.lambda_watchdog_container_activity.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ssm:SendCommand"],
                # No clue what the instance ID will be, so lock it to the ASG:
                resources=["*"],
                conditions={
                    "StringEquals": {
                        "aws:ResourceTag/aws:autoscaling:groupName": auto_scaling_group.auto_scaling_group_name,
                    }
                },
            )
        )
        self.lambda_watchdog_container_activity.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ssm:SendCommand"],
                resources=[f"arn:aws:ssm:{self.region}::document/AWS-RunShellScript"],
            )
        )
        self.lambda_watchdog_container_activity.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ssm:GetCommandInvocation"],
                resources=[f"arn:aws:ssm:{self.region}:{self.account}:*"],
            )
        )
        # Give it permissions to push metric data:
        self.lambda_watchdog_container_activity.add_to_role_policy(
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
        self.metric_watchdog_errors = self.lambda_watchdog_container_activity.metric_errors(
            label="Number of Watchdog Errors",
            unit=cloudwatch.Unit.COUNT,
            # If multiple requests happen in a period, and one isn't an error,
            # use that one.
            statistic=cloudwatch.Stats.MINIMUM,
            period=Duration.minutes(1),
        )
        self.alarm_watchdog_errors = self.metric_watchdog_errors.create_alarm(
            self,
            "AlarmWatchdogErrors",
            alarm_name=f"{leaf_construct_id}-Alarm-Watchdog-Errors",
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
            "RuleWatchdogTrigger",
            rule_name=f"{container_id}-rule-watchdog-trigger",
            description="Trigger Watchdog Lambda every minute, to see how many are using the container",
            schedule=events.Schedule.rate(Duration.minutes(1)),
            targets=[
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events_targets.LambdaFunction.html
                events_targets.LambdaFunction(self.lambda_watchdog_container_activity),
            ],
            # Start disabled, self.lambda_watchdog_container_activity will enable it when instance starts up 
            enabled=False,
        )
