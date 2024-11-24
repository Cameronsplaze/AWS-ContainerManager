
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
        main_config: dict,

        domain_stack: DomainStack,
        container_nested_stack: Container,
        ecs_asg_nested_stack: EcsAsg,
        watchdog_nested_stack: Watchdog,
        asg_state_change_hook_nested_stack: AsgStateChangeHook,
        **kwargs
    ) -> None:
        super().__init__(scope, "DashboardNestedStack", **kwargs)
        container_id_alpha = "".join(e for e in container_id.title() if e.isalpha())

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
                    # The message also contains the timestamp, remove it:
                    "fields @timestamp, substr(@message, 25) as message",
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
                height=6,
                width=12,
                right=[metric_asg_lambda_invocation_count],
                legend_position=cloudwatch.LegendPosition.RIGHT,
                period=Duration.minutes(1),
                statistic="Maximum",
            ),

            ### Show the number of instances, to see when it starts/stops:
            # Should ever only be 0 or 1, and Gauge helps show it's max too.
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.GaugeWidget.html
            cloudwatch.GaugeWidget(
                title="EC2 Instance Count",
                metrics=[watchdog_nested_stack.metric_asg_num_instances],
                left_y_axis=cloudwatch.YAxisProps(min=0, max=1),
                width=4,
                height=5,
            ),

            ## Brief summary of all the alarms, and lets you jump to them directly:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.AlarmStatusWidget.html
            cloudwatch.AlarmStatusWidget(
                title="Alarm Summary",
                width=3,
                height=5,
                alarms=[
                    watchdog_nested_stack.alarm_asg_instance_left_up,
                    watchdog_nested_stack.alarm_container_activity,
                    watchdog_nested_stack.alarm_capacity_provider,
                ],
            ),

            ## Instance Left Up Alarm:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.AlarmWidget.html
            cloudwatch.AlarmWidget(
                title=f"Alarm: {watchdog_nested_stack.alarm_asg_instance_left_up.alarm_name}",
                width=5,
                height=5,
                alarm=watchdog_nested_stack.alarm_asg_instance_left_up,
            ),

            ### All the ASG Traffic in/out
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.GraphWidget.html
            cloudwatch.GraphWidget(
                title="(ASG) All Network Traffic",
                # Only show up to an hour ago:
                height=6,
                width=12,
                right=[
                    watchdog_nested_stack.bytes_per_second_in,
                    watchdog_nested_stack.traffic_dns_metric,
                    # watchdog_nested_stack.watchdog_traffic_metric,
                ],
                legend_position=cloudwatch.LegendPosition.RIGHT,
                period=Duration.minutes(1),
                statistic="Sum",
                ## Left and Right Y-Axis:
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.YAxisProps.html
                # Because of the MetricMath in the graph, units are unknown anyways:
                left_y_axis=cloudwatch.YAxisProps(label="Traffic Packets", show_units=False),
                right_y_axis=cloudwatch.YAxisProps(label="Traffic Amount", show_units=False),
            ),

            ## Container Activity Alarm:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.AlarmWidget.html
            cloudwatch.AlarmWidget(
                title=f"Alarm: {watchdog_nested_stack.alarm_container_activity.alarm_name}",
                width=6,
                height=5,
                alarm=watchdog_nested_stack.alarm_container_activity,
            ),

            ## Capacity Provider Alarm:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.AlarmWidget.html
            cloudwatch.AlarmWidget(
                title=f"Alarm: {watchdog_nested_stack.alarm_capacity_provider.alarm_name}",
                width=6,
                height=5,
                alarm=watchdog_nested_stack.alarm_capacity_provider,
            ),

            ## Show the Container Logs:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.LogQueryWidget.html
            cloudwatch.LogQueryWidget(
                title="Container Logs",
                log_group_names=[container_nested_stack.container_log_group.log_group_name],
                width=12,
                query_lines=[
                    # The message is controlled by code inside the container, no idea if it'll have a timestamp.
                    # Let the user remove the built-in one if it has one, but show it otherwise:
                    f"fields {'@timestamp,' if dashboard_config['ShowContainerTimestamp'] else ''} @message",
                ],
            ),

            ## ECS Container Utilization:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.GraphWidget.html
            cloudwatch.GraphWidget(
                title=f"(ECS) Container Utilization - {main_config["Ec2"]["InstanceType"]}",
                # Only show up to an hour ago:
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
            dashboard_name=f"{application_id}-{container_id_alpha}-Dashboard",
            period_override=cloudwatch.PeriodOverride.AUTO,
            default_interval=dashboard_config["IntervalMinutes"],
            widgets=[dashboard_widgets],
        )
