
"""
This module contains the Dashboard NestedStack class.
"""

from aws_cdk import (
    NestedStack,
    Duration,
    aws_cloudwatch as cloudwatch,
)
from constructs import Construct

from ContainerManager.leaf_stack.domain_stack import DomainStack
## Import the other Nested Stacks:
from . import Container, EcsAsg, Watchdog, AsgStateChangeHook

### Nested Stack info:
# https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.NestedStack.html
class Dashboard(NestedStack):
    """
    This creates the Dashboard Definition to monitor the other stacks.
    It will be moved to the base_stack, once the following bug is fixed:
      - https://github.com/aws/aws-cdk/issues/31393
    """
    def __init__(
        self,
        scope: Construct,
        application_id: str,
        container_id: str,
        volume_config: dict,

        domain_stack: DomainStack,
        container_nested_stack: Container,
        ecs_asg_nested_stack: EcsAsg,
        watchdog_nested_stack: Watchdog,
        asg_state_change_hook_nested_stack: AsgStateChangeHook,
        **kwargs
    ) -> None:
        super().__init__(scope, "DashboardNestedStack", **kwargs)

        #######################
        ### Dashboard stuff ###
        #######################

        ############
        ### Metrics used in the Widgets below:

        ## ASG State Change Invocation Count:
        metric_asg_lambda_invocation_count = asg_state_change_hook_nested_stack.lambda_asg_state_change_hook.metric_invocations(
            unit=cloudwatch.Unit.COUNT,
        )

        ## ASG Traffic In/Out:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Metric.html
        traffic_in_metric = cloudwatch.Metric(
            label="Network In",
            metric_name="NetworkIn",
            namespace="AWS/EC2",
            dimensions_map={"AutoScalingGroupName": ecs_asg_nested_stack.auto_scaling_group.auto_scaling_group_name},
        )
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Metric.html
        traffic_out_metric = cloudwatch.Metric(
            label="Network Out",
            metric_name="NetworkOut",
            namespace="AWS/EC2",
            dimensions_map={"AutoScalingGroupName": ecs_asg_nested_stack.auto_scaling_group.auto_scaling_group_name},
        )
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.MathExpression.html
        total_traffic_metric = cloudwatch.MathExpression(
            label="Total Network Traffic",
            expression="t_in + t_out",
            using_metrics={
                "t_in": traffic_in_metric,
                "t_out": traffic_out_metric,
            },
        )

        ### ASG Traffic PACKETS In/Out Widget:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Metric.html
        traffic_packets_in_metric = cloudwatch.Metric(
            label="Network Packets In",
            metric_name="NetworkPacketsIn",
            namespace="AWS/EC2",
            dimensions_map={"AutoScalingGroupName": ecs_asg_nested_stack.auto_scaling_group.auto_scaling_group_name},
        )
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Metric.html
        traffic_packets_out_metric = cloudwatch.Metric(
            label="Network Packets Out",
            metric_name="NetworkPacketsOut",
            namespace="AWS/EC2",
            dimensions_map={"AutoScalingGroupName": ecs_asg_nested_stack.auto_scaling_group.auto_scaling_group_name},
        )
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.MathExpression.html
        total_packets_metric = cloudwatch.MathExpression(
            label="Total Packets Traffic",
            expression="t_p_in + t_p_out",
            using_metrics={
                "t_p_in": traffic_packets_in_metric,
                "t_p_out": traffic_packets_out_metric,
            },
        )

        ## EC2 Service Metrics:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.Ec2Service.html#metricwbrcpuwbrutilizationprops
        cpu_utilization_metric = ecs_asg_nested_stack.ec2_service.metric_cpu_utilization()
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.Ec2Service.html#metricwbrmemorywbrutilizationprops
        memory_utilization_metric = ecs_asg_nested_stack.ec2_service.metric_memory_utilization()

        ############
        ### Widgets Here. The order here is how they'll appear in the dashboard.
        dashboard_widgets = [

            ## Route53 DNS logs for spinning up the system:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.LogQueryWidget.html
            cloudwatch.LogQueryWidget(
                title="DNS Traffic - Hook to Start Up System",
                log_group_names=[domain_stack.route53_query_log_group.log_group_name],
                region=domain_stack.region,
                width=12,
                query_lines=[
                    "fields @message",
                    # Spaces on either side, just like SubscriptionFilter, to not
                    # trigger on the "_tcp" query that pairs with the normal one:
                    f"filter @message like /{domain_stack.log_dns_filter}/",
                ],
            ),

            ## Lambda Invocation count for after AWS State Changes
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.GraphWidget.html
            cloudwatch.GraphWidget(
                title="(Lambda) ASG State Change Invocations",
                # Only show up to an hour ago:
                start=f"-PT{volume_config["IntervalMinutes"].to_minutes()}M",
                height=6,
                width=12,
                right=[metric_asg_lambda_invocation_count],
                legend_position=cloudwatch.LegendPosition.RIGHT,
                period=Duration.minutes(1),
                statistic="Sum",
            ),

            ## Show Instances, to easily see when it starts/stops.
            # Should only ever be 0 or 1, but this widget displays that the best.
            cloudwatch.SingleValueWidget(
                title="Instance Count",
                width=3,
                height=4,
                metrics=[watchdog_nested_stack.metric_asg_num_instances],
            ),

            ## Brief summary of all the alarms, and lets you jump to them directly:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.AlarmStatusWidget.html
            cloudwatch.AlarmStatusWidget(
                title=f"Alarm Summary ({container_id})",
                width=3,
                height=4,
                alarms=[
                    watchdog_nested_stack.alarm_container_activity,
                    watchdog_nested_stack.alarm_watchdog_errors,
                    watchdog_nested_stack.alarm_asg_instance_left_up,
                ],
            ),

            ## Container Activity Alarm:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.AlarmWidget.html
            cloudwatch.AlarmWidget(
                title=f"Alarm: {watchdog_nested_stack.alarm_container_activity.alarm_name}",
                width=6,
                height=4,
                alarm=watchdog_nested_stack.alarm_container_activity,
            ),

            ### All the ASG Traffic in/out
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.GraphWidget.html
            cloudwatch.GraphWidget(
                title="(ASG) All Network Traffic",
                # Only show up to an hour ago:
                start=f"-PT{volume_config["IntervalMinutes"].to_minutes()}M",
                height=6,
                width=12,
                left=[traffic_packets_in_metric, traffic_packets_out_metric, total_packets_metric],
                right=[traffic_in_metric, traffic_out_metric, total_traffic_metric],
                legend_position=cloudwatch.LegendPosition.RIGHT,
                period=Duration.minutes(1),
                statistic="Sum",
                ## Left and Right Y-Axis:
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.YAxisProps.html
                # Because of the MetricMath in the graph, units are unknown anyways:
                left_y_axis=cloudwatch.YAxisProps(label="Traffic Packets", show_units=False),
                right_y_axis=cloudwatch.YAxisProps(label="Traffic Amount", show_units=False),
            ),

            ## Instance Left Up Alarm:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.AlarmWidget.html
            cloudwatch.AlarmWidget(
                title=f"Alarm: {watchdog_nested_stack.alarm_asg_instance_left_up.alarm_name}",
                width=6,
                height=4,
                alarm=watchdog_nested_stack.alarm_asg_instance_left_up,
            ),

            ## WatchDog Errors Alarm:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.AlarmWidget.html
            cloudwatch.AlarmWidget(
                title=f"Alarm: {watchdog_nested_stack.alarm_watchdog_errors.alarm_name}",
                width=6,
                height=4,
                alarm=watchdog_nested_stack.alarm_watchdog_errors,
            ),

            ## Show the Container Logs:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.LogQueryWidget.html
            cloudwatch.LogQueryWidget(
                title="Container Logs",
                log_group_names=[container_nested_stack.container_log_group.log_group_name],
                width=12,
                query_lines=[
                    "fields @message",
                ],
            ),

            ## ECS Container Utilization:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.GraphWidget.html
            cloudwatch.GraphWidget(
                title=f"(ECS) Container Utilization - {ecs_asg_nested_stack.instance_type}",
                # Only show up to an hour ago:
                start=f"-PT{volume_config["IntervalMinutes"].to_minutes()}M",
                height=6,
                width=12,
                right=[cpu_utilization_metric, memory_utilization_metric],
                # But have both keys in the same spot, on the right:
                legend_position=cloudwatch.LegendPosition.RIGHT,
                period=Duration.minutes(1),
                statistic="Maximum",
            ),

        ]

        ############
        ### Finally create the Dashboard itself:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Dashboard.html
        self.dashboard = cloudwatch.Dashboard(
            self,
            "CloudwatchDashboard",
            dashboard_name=f"{application_id}-{container_id}-Dashboard",
            period_override=cloudwatch.PeriodOverride.AUTO,
            default_interval=volume_config["IntervalMinutes"],
            widgets=[dashboard_widgets],
        )
