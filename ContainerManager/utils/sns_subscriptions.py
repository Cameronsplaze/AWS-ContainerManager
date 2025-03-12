
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
    # subscriptions = {
    #     "Email": "email1@gmail.com email2@gmail.com",
    #     "HTTPS": "https://example.com https://example2.com",
    #     # ...
    # }
    for protocol, endpoints in subscriptions.items():
        protocol = getattr(sns.SubscriptionProtocol, protocol.upper())
        for endpoint in endpoints.split(" "):
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_sns.Subscription.html
            sns.Subscription(
                context,
                "sns-notify-subscription",
                protocol=protocol,
                endpoint=endpoint,
                topic=sns_topic,
            )
