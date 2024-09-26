
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
        **kwargs
    ) -> None:
        super().__init__(scope, "DashboardNestedStack", **kwargs)
        ## YES This isn't the "optimum" way if the dashboard is in the same
        # stack as everything it's watching. Once the bug listed above is fixed,
        # I want to move this nested stack to the base_stack, and have ALL the
        # leaf_stacks push to the same dashboard. That way you can see how they
        # compare to one another easily too.

        #######################
        ### Dashboard stuff ###
        #######################
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Dashboard.html
        self.dashboard = cloudwatch.Dashboard(
            self,
            "CloudwatchDashboard",
            dashboard_name=f"{leaf_construct_id}-dashboard",
            period_override=cloudwatch.PeriodOverride.AUTO,
        )

        ### There's a bug rn where you can't create blank widgets,
        # So TMP create a blank metric to attach to them:
        # BUG: https://github.com/aws/aws-cdk/issues/31393
        # DOCS: https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Metric.html
        blank_metric = cloudwatch.Metric(
            metric_name="blank",
            namespace="blank",
            period=Duration.minutes(1),
            statistic="Maximum",
        )

        # "Namespace" the widgets. All the leaf stacks will need to access them, but
        #    I don't want to have a ton of widgets directly in "self". Plus now we can
        #    loop over the dict to add to the dashboard instead of adding each one manually.
        self.widgets = {
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.GraphWidget.html
            "AutoScalingGroup-Traffic": cloudwatch.GraphWidget(
                height=8,
                width=12,
                left=[blank_metric],
            ),
        }
        # Add the widgets to the dashboard:
        for widget in self.widgets.values():
            self.dashboard.add_widgets(widget)
