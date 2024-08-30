
"""
sns_subscriptions.py

Broken into it's own file since it's used in both the base and leaf stacks,
AND since it takes 'context', it can't be created in the 'config_loader.py' file.
"""

from aws_cdk import (
    aws_sns as sns,
)


def add_sns_subscriptions(context, sns_topic: sns.Topic, subscriptions: dict) -> None:
    """
    Add SNS Subscriptions to an SNS Topic
        (Normally 'subscriptions' is the 'Alert Subscription' block from the config file)
    """
    for subscription in subscriptions:
        # All of the error checking is in the config parser/loader:
        protocol, address = list(subscription.items())[0]
        ## Email with a SNS Subscription:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_sns.Subscription.html
        sns.Subscription(
            context,
            "sns-notify-subscription",
            protocol=protocol,
            endpoint=address,
            topic=sns_topic,
        )
