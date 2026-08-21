
"""
This module contains the Dashboard NestedStack class.
"""

from aws_cdk import (
    NestedStack,
    Duration,
    aws_cloudwatch as cloudwatch,
)
from constructs import Construct

from ContainerManager.leaf_stack_group.domain_stack import DomainStack
## Import the other Nested Stacks:
from .Container import Container
from .Volume import Volume
from .EcsAsg import EcsAsg
from .Watchdog import Watchdog
from .AsgStateChangeHook import AsgStateChangeHook

TRAFFIC_IN_LABEL = "Traffic (KiB / min)"

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
        main_config: dict,

        domain_stack: DomainStack,
        container_nested_stack: Container,
        volume_nested_stack: Volume,
        ecs_asg_nested_stack: EcsAsg,
        watchdog_nested_stack: Watchdog,
        asg_state_change_hook_nested_stack: AsgStateChangeHook,
        **kwargs
    ) -> None:
        super().__init__(scope, "DashboardNestedStack", **kwargs)
        container_id_alpha = "".join(e for e in container_id.title() if e.isalnum())

        #######################
        ### Dashboard stuff ###
        #######################
        # Config options for specifically this stack:
        dashboard_config = main_config["Dashboard"]

        ############
        ### Metrics used in the Widgets below:

        ## ASG State Change Invocation Count:
        metric_asg_lambda_invocation_count = asg_state_change_hook_nested_stack.lambda_asg_state_change_hook.metric_invocations(
            unit=cloudwatch.Unit.COUNT,
            statistic="Maximum",
            period=Duration.minutes(1),
        )

        ############
        ### Widgets Here. The order here is how they'll appear in the dashboard.
        dashboard_widgets: list[cloudwatch.IWidget] = []

        ## Route53 DNS logs for spinning up the system:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.LogQueryWidget.html
        dashboard_widgets.append(
            cloudwatch.LogQueryWidget(
                title=f"(DNS Traffic) Start's Up System - [{domain_stack.region}: {domain_stack.route53_query_log_group.log_group_name}]",
                log_group_names=[domain_stack.route53_query_log_group.log_group_name],
                region=domain_stack.region,
                width=12,
                height=4,
                query_lines=[
                    # The message *also* contains the timestamp too, remove it:
                    "fields @timestamp, substr(@message, 25) as message",
                    f"filter @message like /{domain_stack.dns_log_query_filter}/",
                ],
            )
        )

        
        ## Lambda Invocation count for after AWS State Changes
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.GraphWidget.html
        dashboard_widgets.append(
            cloudwatch.GraphWidget(
                # TODO: Change this to show BOTH invocations and errors, AND add in the backup lambda (at least)
                title="(Lambda) ASG State Change Invocations",
                # Only show up to an hour ago:
                height=6,
                width=12,
                right=[metric_asg_lambda_invocation_count],
                legend_position=cloudwatch.LegendPosition.RIGHT,
                ## Only shows units when graph has data. This changes that:
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.YAxisProps.html
                right_y_axis=cloudwatch.YAxisProps(label=metric_asg_lambda_invocation_count.unit.value.title(), show_units=False), # type: ignore[union-attr]
            )
        )

        ### Show the number of instances, to see when it starts/stops:
        # Should ever only be N/A or 1, and Gauge helps show it's max too.
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.GaugeWidget.html
        dashboard_widgets.append(
            cloudwatch.GaugeWidget(
                title="EC2 Instance Count",
                metrics=[watchdog_nested_stack.instance_is_up],
                left_y_axis=cloudwatch.YAxisProps(min=0, max=1),
                width=4,
                height=6,
                # As soon as you see data, turn on. We don't care what the data is in this case:
                live_data=True,
                # Only look back same as the metric period to get last datapoint:
                # (needed because "no-data" means 0, it never posts a metric of '0')
                start=f"-PT{watchdog_nested_stack.instance_is_up.period.to_minutes()}M",
            )
        )

        ## Brief summary of all the alarms, and lets you jump to them directly:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.AlarmStatusWidget.html
        dashboard_widgets.append(
            cloudwatch.AlarmStatusWidget(
                # TODO: Add the Backup Fail Alarm here.
                title=f"Alarm Summary [{domain_stack.sub_domain_name}]",
                width=4,
                height=6,
                # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_cloudwatch/AlarmStatusWidgetSortBy.html#aws_cdk.aws_cloudwatch.AlarmStatusWidgetSortBy
                sort_by=cloudwatch.AlarmStatusWidgetSortBy.STATE_UPDATED_TIMESTAMP,
                alarms=[
                    watchdog_nested_stack.alarm_asg_instance_left_up,
                    watchdog_nested_stack.alarm_container_activity,
                    watchdog_nested_stack.alarm_break_crash_loop_count,
                ],
            )
        )

        ## Crash Loop Alarm:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.AlarmWidget.html
        dashboard_widgets.append(
            cloudwatch.AlarmWidget(
                title=f"(Alarm) {watchdog_nested_stack.alarm_break_crash_loop_count.alarm_name}",
                width=4,
                height=6,
                alarm=watchdog_nested_stack.alarm_break_crash_loop_count,
            )
        )

        ### All the ASG Traffic in/out
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.GraphWidget.html
        dashboard_widgets.append(
            cloudwatch.GraphWidget(
                title="(ASG) All Network Traffic",
                height=6,
                width=12,
                right=[
                    # watchdog_nested_stack.kb_in_per_minute,
                    # volume_nested_stack.kb_out_per_min,
                    watchdog_nested_stack.traffic_dns_metric,
                    ecs_asg_nested_stack.container_traffic_in,
                    # *volume_nested_stack.traffic_out_metrics.values(),
                ],
                legend_position=cloudwatch.LegendPosition.RIGHT,
                period=Duration.minutes(1),
                statistic="Sum",
                ## Left and Right Y-Axis:
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.YAxisProps.html
                # Because of the MetricMath in the graph, units are unknown anyways:
                right_y_axis=cloudwatch.YAxisProps(label=TRAFFIC_IN_LABEL, show_units=False),
            )
        )

        ## Container Activity Alarm:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.AlarmWidget.html
        dashboard_widgets.append(
            cloudwatch.AlarmWidget(
                title=f"(Alarm) {watchdog_nested_stack.alarm_container_activity.alarm_name}",
                width=8,
                height=6,
                alarm=watchdog_nested_stack.alarm_container_activity,
                ## Doesn't show the units anyways:
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.YAxisProps.html
                left_y_axis=cloudwatch.YAxisProps(label=TRAFFIC_IN_LABEL, show_units=False),
            )
        )

        ## Instance Left Up Alarm:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.AlarmWidget.html
        dashboard_widgets.append(
            cloudwatch.AlarmWidget(
                title=f"(Alarm) {watchdog_nested_stack.alarm_asg_instance_left_up.alarm_name}",
                width=4,
                height=6,
                alarm=watchdog_nested_stack.alarm_asg_instance_left_up,
                ## Doesn't show the units anyways:
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.YAxisProps.html
                left_y_axis=cloudwatch.YAxisProps(label="Bool", show_units=False),
            )
        )

        ## Show the Container Logs:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.LogQueryWidget.html
        dashboard_widgets.append(
            cloudwatch.LogQueryWidget(
                title=f"Container's Logs - [{self.region}: {container_nested_stack.container_log_group.log_group_name}]",
                log_group_names=[container_nested_stack.container_log_group.log_group_name],
                height=10,
                width=12,
                query_lines=[
                    # The message is controlled by code inside the container, no idea if it'll have a timestamp.
                    # Let the user remove the built-in one if it has one, but show it otherwise:
                    f"fields {'@timestamp,' if dashboard_config['ShowContainerLogTimestamp'] else ''} @message",
                ],
            )
        )

        ### CPU Doesn't change Ec2 Host vs Container:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.Ec2Service.html#metricwbrcpuwbrutilizationprops
        cpu_utilization_percent = ecs_asg_nested_stack.ec2_service.metric_cpu_utilization(
            label=f"CPU Utilization [{main_config['Ec2']['VCpuInfo']['DefaultVCpus']} vCPU's]",
            statistic="Average",
        )

        ### Memory: Built-in metrics are "used / soft-limit". we want "used / ec2-max":
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.Ec2Service.html#metricwbrmemorywbrutilizationprops
        memory_task_percent = ecs_asg_nested_stack.ec2_service.metric_memory_utilization(statistic="Average")
        memory_task_limit = container_nested_stack.container.render_container_definition().memory_reservation
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.MathExpression.html
        memory_utilization_percent = cloudwatch.MathExpression(
            label=f"Memory Utilization [{main_config['Ec2']['MemoryInfo']['SizeInMiB'] / 1024} GB]",
            # Subtract 1GB in the expression, because what the host uses doesn't appear in the metric anyways.
            expression=f"memory_utilization * {memory_task_limit} / ({main_config['Ec2']['MemoryInfo']['SizeInMiB']} - 1024)",
            using_metrics={
                "memory_utilization": memory_task_percent,
            },
            period=Duration.minutes(1),
        )
        ### GPU Metrics:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.GraphWidget.html
        gpu_utilization_metric = cloudwatch.Metric(
            label=f"GPU Utilization - [{len(main_config['Ec2']['GpuInfo']['Gpus']) if main_config['Ec2']['GpuExists'] else 0} GPU's]",
            namespace="ECS/ContainerInsights",
            metric_name="ContainerGPUUtilization",
            dimensions_map={
                "ClusterName": ecs_asg_nested_stack.ecs_cluster.cluster_name,
            },
            period=Duration.minutes(1),
            statistic="Sum",
        )
        gpu_memory_utilization_metric = cloudwatch.Metric(
            label=f"GPU Memory Utilization - [{len(main_config['Ec2']['GpuInfo']['Gpus']) if main_config['Ec2']['GpuExists'] else 0} GPU's]",
            namespace="ECS/ContainerInsights",
            metric_name="ContainerGPUMemoryUtilization",
            dimensions_map={
                "ClusterName": ecs_asg_nested_stack.ecs_cluster.cluster_name,
            },
            period=Duration.minutes(1),
            statistic="Sum",
        )
        ## Ec2 Utilization Graph:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.GraphWidget.html
        dashboard_widgets.append(
            cloudwatch.GraphWidget(
                title=f"(ECS) Container Utilization - [{main_config['Ec2']['InstanceType']}]",
                # Only show up to an hour ago:
                height=6,
                width=12,
                right=[
                    cpu_utilization_percent,
                    memory_utilization_percent,
                    gpu_utilization_metric,
                    gpu_memory_utilization_metric,
                ],
                # But have both keys in the same spot, on the right:
                legend_position=cloudwatch.LegendPosition.RIGHT,
                period=Duration.minutes(1),
                statistic="Maximum",
                ## Only shows units when graph has data. This changes that:
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.YAxisProps.html
                right_y_axis=cloudwatch.YAxisProps(label="Percent", show_units=False), # type: ignore
            )
        )

        ############
        ### Finally create the Dashboard itself:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Dashboard.html
        self.dashboard = cloudwatch.Dashboard(
            self,
            "CloudwatchDashboard",
            dashboard_name=f"{application_id}-{container_id_alpha}-Dashboard",
            period_override=cloudwatch.PeriodOverride.AUTO,
            default_interval=dashboard_config["IntervalMinutes"],
            widgets=[dashboard_widgets],
        )
