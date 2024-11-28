
"""
This module contains the Watchdog NestedStack class.
"""

from aws_cdk import (
    NestedStack,
    Duration,
    aws_ecs as ecs,
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
        ecs_cluster: ecs.Cluster,
        ecs_capacity_provider: ecs.AsgCapacityProvider,
        **kwargs,
    ) -> None:
        super().__init__(scope, "WatchdogNestedStack", **kwargs)

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

        ################################
        ## Instance Up too-long Logic ##
        ################################
        ## Grab the built-in IN_SERVICE_INSTANCES metric and load into cdk:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Metric.html
        self.metric_asg_num_instances = cloudwatch.Metric(
            label="Number of Instances",
            metric_name="GroupInServiceInstances",
            namespace="AWS/AutoScaling",
            dimensions_map={
                "AutoScalingGroupName": auto_scaling_group.auto_scaling_group_name,
            },
            period=Duration.minutes(1),
            statistic="Maximum",
        )
        ## And the alarm to flag if the instance is up too long:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Alarm.html
        duration_before_alarm = watchdog_config["InstanceLeftUp"]["DurationHours"].to_minutes()
        self.alarm_asg_instance_left_up = self.metric_asg_num_instances.create_alarm(
            self,
            "AlarmInstanceLeftUp",
            alarm_name=f"Instance Left Up ({leaf_construct_id})",
            alarm_description="To warn if the instance is up too long",
            ### This way if the period changes, this will stay the same duration:
            # Total Duration = Number of Periods * Period length... so
            # Number of Periods = Total Duration / Period length
            evaluation_periods=int(duration_before_alarm / self.metric_asg_num_instances.period.to_minutes()),
            threshold=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.MISSING,
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

        ##########################################
        ## Container Crash-loop Detection Logic ##
        ##########################################
        # If the task can start, but then something in their entrypoint throws, ecs will just
        # restart it. (And because you technically started, it won't trip the circuit breaker).
        # This logic will (hopefully) see the task spinning up and down constantly, and spin
        # the ec2 instance to avoid paying for something you're not using.


        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Metric.html
        # metric_capacity_provider = cloudwatch.Metric(
        #     label="Capacity Provider Reservation (percent)",
        #     metric_name="CapacityProviderReservation",
        #     namespace="AWS/ECS/ManagedScaling",
        #     dimensions_map={
        #         "ClusterName": ecs_cluster.cluster_name,
        #         "CapacityProviderName": ecs_capacity_provider.capacity_provider_name,
        #     },
        #     period=Duration.minutes(1),
        #     statistic="Minimum",
        # )

        # # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Alarm.html
        # self.alarm_capacity_provider = metric_capacity_provider.create_alarm(
        #     self,
        #     "AlarmCapacityProvider",
        #     alarm_name=f"Capacity Provider ({leaf_construct_id})",
        #     alarm_description="Trigger if the container is crashing too often",
        #     threshold=100,
        #     comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
        #     ## In the last 6 points, 2 must alarm to trigger:
        #     # (When tasks fail, it creates a zig-zag pattern in the metric).
        #     datapoints_to_alarm=2,
        #     evaluation_periods=6,
        # )
        # ## Call this if switching to ALARM:
        # # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Alarm.html#addwbralarmwbractionactions
        # self.alarm_capacity_provider.add_alarm_action(
        #     cloudwatch_actions.AutoScalingAction(self.scale_down_asg_action)
        # )

        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events.Rule.html
        self.rule_break_crash_loop = events.Rule(
            self,
            "RuleBreakCrashLoop",
            rule_name=f"{container_id}-rule-break-crash-loop",
            description="Trigger if the container is crashing too often",
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events.EventPattern.html
            event_pattern=events.EventPattern(
                source=["aws.ecs"],
                detail_type=["ECS Task State Change"],
                detail={
                    "clusterArn": [ecs_cluster.cluster_arn],
                    "capacityProviderName": [ecs_capacity_provider.capacity_provider_name],
                    # If the container crashes:
                    "stopCode": ["EssentialContainerExited"],
                    "containers": {
                        "exitCode": [{"anything-but": 0}],
                    },
                },
            ),
            targets=[
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events_targets.SnsTopic.html
                events_targets.SnsTopic(
                    base_stack_sns_topic,
                ),
                # TODO: See if cross-region works, and you can use the trigger-start-system lambda? But I guess you'd have to stop asg instead...
            ],
        )
