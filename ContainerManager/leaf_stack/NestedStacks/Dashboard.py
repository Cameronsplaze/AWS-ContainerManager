
"""
This module contains the Dashboard NestedStack class.
"""

from aws_cdk import (
    NestedStack,
    Duration,
    aws_cloudwatch as cloudwatch,
)
from constructs import Construct

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
        leaf_construct_id: str,
        dashboard_widgets: list[tuple[int, cloudwatch.IWidget]],
        application_id: str,
        container_id: str,
        route53_dns_log_group_name: str,
        route53_dns_region: str,
        route53_dns_sub_domain_name: str,
        **kwargs
    ) -> None:
        super().__init__(scope, "DashboardNestedStack", **kwargs)

        #######################
        ### Dashboard stuff ###
        #######################
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Dashboard.html
        self.dashboard = cloudwatch.Dashboard(
            self,
            "CloudwatchDashboard",
            dashboard_name=f"{application_id}-{container_id}-Dashboard",
            period_override=cloudwatch.PeriodOverride.AUTO,
            default_interval=Duration.hours(1),
        )

        #############
        ### Widgets for data *OUTSIDE* of this Main Managing Stack:

        ## Route53 DNS logs for spinning up the system:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.LogQueryWidget.html
        dns_logs_widget = cloudwatch.LogQueryWidget(
            title="DNS Traffic - Hook to Start Up System",
            log_group_names=[route53_dns_log_group_name],
            region=route53_dns_region,
            width=12,
            query_lines=[
                "fields @message",
                # Spaces on either side, just like SubscriptionFilter, to not
                # trigger on the "_tcp" query that pairs with the normal one:
                f"filter @message like / {route53_dns_sub_domain_name} /",
            ],
        )
        dashboard_widgets.append((1, dns_logs_widget))

        ### Add the widgets to the dashboard:
        widgets = [widget for _, widget in sorted(dashboard_widgets, key=lambda x: x[0])]
        self.dashboard.add_widgets(*widgets)
