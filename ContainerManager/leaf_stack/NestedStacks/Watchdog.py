
"""
This module contains the Watchdog NestedStack class.
"""

from aws_cdk import (
    NestedStack,
    Duration,
    RemovalPolicy,
    aws_lambda,
    aws_iam as iam,
    aws_ecs as ecs,
    aws_logs as logs,
    aws_sns as sns,
    aws_events as events,
    aws_events_targets as events_targets,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cloudwatch_actions,
    aws_autoscaling as autoscaling,
)
from constructs import Construct

class Watchdog(NestedStack):
    """
    This sets up the logic for watching the container for
    connections, and scaling down the ASG when none are found.
    """
    def __init__(
        self,
        scope: Construct,
        leaf_construct_id: str,
        container_id: str,
        watchdog_config: dict,
        auto_scaling_group: autoscaling.AutoScalingGroup,
        base_stack_sns_topic: sns.Topic,
        leaf_stack_sns_topic: sns.Topic,
        ecs_cluster: ecs.Cluster,
        ecs_capacity_provider: ecs.AsgCapacityProvider,
        **kwargs,
    ) -> None:
        super().__init__(scope, "WatchdogNestedStack", **kwargs)
        container_id_alpha = "".join(e for e in container_id.title() if e.isalpha())

        ## Scale down ASG to 0 if this is ever triggered:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_autoscaling.StepScalingAction.html
        # https://medium.com/swlh/deploy-your-auto-scaling-stack-with-aws-cdk-abae64f8e6b6
        self.scale_down_asg_action = autoscaling.StepScalingAction(self,
            "ScaleDownAsgAction",
            auto_scaling_group=auto_scaling_group,
            adjustment_type=autoscaling.AdjustmentType.EXACT_CAPACITY,
        )
        ## There's a bug where you HAVE to set lower_bound or upper_bound,
        ##    AND float("inf") isn't supported.
        # Set -inf to 0:
        self.scale_down_asg_action.add_adjustment(adjustment=0, upper_bound=0)
        # Set 0 to inf:
        self.scale_down_asg_action.add_adjustment(adjustment=0, lower_bound=0)


        ############################
        ## Traffic IN Alarm Logic ##
        ############################
        ## These variables are also used in link_together_stack.py, so
        #    if someone is connecting, it'll reset the alarm:
        self.threshold = watchdog_config["Threshold"]
        self.metric_namespace = leaf_construct_id
        self.metric_unit = cloudwatch.Unit.COUNT
        self.metric_dimension_map = {
            "ContainerNameID": container_id,
        }
        # And the metric it resets with:
        self.traffic_dns_metric = cloudwatch.Metric(
            label="DNS Traffic",
            metric_name="DNSTraffic",
            namespace=self.metric_namespace,
            dimensions_map=self.metric_dimension_map,
            period=Duration.minutes(1),
            statistic="Maximum",
            unit=self.metric_unit,
        )

        ## ASG Traffic In:
        # Originally Added 'Out' too, but it was too noisy. You only care about
        # people connecting to container, or container downloading anyways.
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Metric.html
        traffic_in_metric = cloudwatch.Metric(
            label="Network In",
            metric_name="NetworkIn",
            namespace="AWS/EC2",
            dimensions_map={"AutoScalingGroupName": auto_scaling_group.auto_scaling_group_name},
            period=Duration.minutes(1),
        )
        ## Get Bytes per Second
        # https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/viewing_metrics_with_cloudwatch.html#ec2-cloudwatch-metrics
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.MathExpression.html
        # BUT the DIFF_TIME function can cause divide by 0, and errors on first metric. Just grab period instead:
        self.bytes_per_second_in = cloudwatch.MathExpression(
            label="Bytes IN per Second",
            expression=f"b_in/{traffic_in_metric.period.to_seconds()}",
            using_metrics={
                "b_in": traffic_in_metric,
            },
        )

        ## Combine two metrics here before creating the alarm:
        # Docs: https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.MathExpression.html
        # Info: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/using-metric-math.html
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.MathExpression.html
        self.watchdog_traffic_metric = cloudwatch.MathExpression(
            label="Watchdog Container Traffic",
            expression="traffic + dns_hit",
            using_metrics={
                "traffic": self.bytes_per_second_in,
                "dns_hit": self.traffic_dns_metric,
            },
            period=Duration.minutes(1),
        )

        ## Trigger if 0 people are connected for too long:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Metric.html#createwbralarmscope-id-props
        #       Total Duration = Number of Periods * Period length... so
        #       Number of Periods = Total Duration / Period length
        evaluation_periods = int(watchdog_config["MinutesWithoutConnections"].to_minutes() / self.watchdog_traffic_metric.period.to_minutes())
        self.alarm_container_activity = self.watchdog_traffic_metric.create_alarm(
            self,
            "AlarmContainerActivity",
            alarm_name=f"Container Activity ({leaf_construct_id})",
            alarm_description="Trigger if 0 people are connected for too long",
            evaluation_periods=evaluation_periods,
            threshold=self.threshold,
            comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.MISSING,
        )
        ## Call this if switching to ALARM:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Alarm.html#addwbralarmwbractionactions
        self.alarm_container_activity.add_alarm_action(
            cloudwatch_actions.AutoScalingAction(self.scale_down_asg_action)
        )


        ################################
        ## Instance Up too-long Logic ##
        ################################

        ## Use the `traffic_in_metric` from above. If it has data, the instance is up:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.MathExpression.html
        self.instance_is_up = cloudwatch.MathExpression(
            # Doing N/A or 1, so alarms are blank if no instance/data:
            # (save on cloudwatch api calls when system is off)
            label="Instance is Up (Bool)",
            expression="network_in >= 0",
            using_metrics={
                "network_in": traffic_in_metric,
            },
            period=traffic_in_metric.period,
        )

        ## Trigger if the instance is up too long:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Alarm.html
        duration_before_alarm = watchdog_config["InstanceLeftUp"]["DurationHours"].to_minutes()
        self.alarm_asg_instance_left_up = self.instance_is_up.create_alarm(
            self,
            "AlarmInstanceLeftUp",
            alarm_name=f"Instance Left Up ({leaf_construct_id})",
            alarm_description="To warn if the instance is up too long",
            ### This way if the period changes, this will stay the same duration:
            # Total Duration = Number of Periods * Period length... so
            # Number of Periods = Total Duration / Period length
            evaluation_periods=int(duration_before_alarm / self.instance_is_up.period.to_minutes()),
            threshold=0,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            # Missing data means instance is off:
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )

        ## Actually email admin if this is triggered:
        #   (No need to add the other sns_topic too, only admin would ever care about this.)
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Alarm.html#addwbralarmwbractionactions
        self.alarm_asg_instance_left_up.add_alarm_action(
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch_actions.SnsAction.html
            cloudwatch_actions.SnsAction(base_stack_sns_topic)
        )
        if watchdog_config["InstanceLeftUp"]["ShouldStop"]:
            self.alarm_asg_instance_left_up.add_alarm_action(
                cloudwatch_actions.AutoScalingAction(self.scale_down_asg_action)
            )


        ##########################################
        ## Container Crash-loop Detection Logic ##
        ##########################################
        # If either the task can't start, or the container throws after starting, this
        # will spin down the ASG (which will in-turn spin down the task). Without this,
        # ECS would try to keep running the task, and it downloading would stop the
        # Watchdog traffic metric above from spinning down the system.

        ## Log group for the lambda function:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_logs.LogGroup.html
        log_group_break_crash_loop = logs.LogGroup(
            self,
            "LogGroupStartSystem",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
            log_group_name=f"/aws/lambda/{container_id_alpha}-break-crash-loop",
        )

        ## Policy/Role for lambda function:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_iam.Role.html
        role_break_crash_loop = iam.Role(
            self,
            "AsgStateChangeHookRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Role for the AsgStateChangeHook lambda function.",
        )
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_iam.Policy.html
        policy_break_crash_loop = iam.Policy(
            self,
            "AsgStateChangeHookPolicy",
            roles=[role_break_crash_loop],
            # Statements added at the end of this file:
            statements=[],
        )

        ## Lambda function spin down ASG if container errors/throws:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_lambda.Function.html
        self.lambda_break_crash_loop = aws_lambda.Function(
            self,
            "BreakCrashLoop",
            description=f"{container_id_alpha}-break-crash-loop: Triggered if container throws, and spins down ASG.",
            code=aws_lambda.Code.from_asset("./ContainerManager/leaf_stack/lambda/spin-down-asg-on-error/"),
            handler="main.lambda_handler",
            runtime=aws_lambda.Runtime.PYTHON_3_12,
            log_group=log_group_break_crash_loop,
            role=role_break_crash_loop,
            environment={
                "ASG_NAME": auto_scaling_group.auto_scaling_group_name,
            },
        )
        ### Lambda Permissions:
        # Give it write to it's own log group:
        log_group_break_crash_loop.grant_write(self.lambda_break_crash_loop)
        # Give it permissions to update the ASG desired_capacity:
        policy_break_crash_loop.add_statements(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "autoscaling:UpdateAutoScalingGroup",
                ],
                resources=[auto_scaling_group.auto_scaling_group_arn],
            )
        )

        ### Check for the Task Failing:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events.Rule.html
        self.rule_break_crash_loop = events.Rule(
            self,
            "RuleBreakCrashLoop",
            rule_name=f"{container_id}-rule-break-crash-loop",
            description="Spin down the ASG if the container crashes or can't start",
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events.EventPattern.html
            event_pattern=events.EventPattern(
                source=["aws.ecs"],
                detail_type=["ECS Task State Change"],
                detail={
                    ## For matching event detail patterns:
                    # https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-create-pattern-operators.html
                    "clusterArn": [ecs_cluster.cluster_arn],
                    "capacityProviderName": [ecs_capacity_provider.capacity_provider_name],
                    "desiredStatus": ["STOPPED"],
                    "$or": [
                        # If the container doesn't start at all:
                        {
                            "stopCode": ["TaskFailedToStart"],
                        },
                        # If the container starts, then throws after:
                        {
                            "stopCode": ["EssentialContainerExited"],
                            "containers": {
                                "exitCode": [{"anything-but": 0}],
                            },
                        }
                    ],
                },
            ),
            targets=[
                ## NOTE: Not doing SNS here since it can trigger 2-4 times before
                # lambda below finally disables it. Do in alarm instead to only get 1.
                ## https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events_targets.LambdaFunction.html
                events_targets.LambdaFunction(self.lambda_break_crash_loop),
            ],
        )

        metric_break_crash_loop_count = self.lambda_break_crash_loop.metric_invocations(
            unit=cloudwatch.Unit.COUNT,
            statistic="Maximum",
            period=Duration.minutes(1),
        )
        self.alarm_break_crash_loop_count = metric_break_crash_loop_count.create_alarm(
            self,
            "AlarmBreakCrashLoop",
            alarm_name=f"Break Crash Loop ({leaf_construct_id})",
            alarm_description="Spin down the ASG if the container crashes or can't start",
            threshold=0,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            evaluation_periods=1,
            # Missing data means instance is off:
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        ## Call these if switching to ALARM:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Alarm.html#addwbralarmwbractionactions
        self.alarm_break_crash_loop_count.add_alarm_action(
            cloudwatch_actions.SnsAction(base_stack_sns_topic)
        )
        self.alarm_break_crash_loop_count.add_alarm_action(
            cloudwatch_actions.SnsAction(leaf_stack_sns_topic)
        )
