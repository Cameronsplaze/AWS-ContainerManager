
"""
sns_subscriptions.py

Broken into it's own file since it's used in both the base and leaf stacks,
AND since it takes 'context', it can't be created in the 'config_loader.py' file.
"""

from schema import Schema, And, Use, Optional

from aws_cdk import (
    aws_sns as sns,
)

sns_schema = Schema({
    Optional(And(
        ## KEY
        # You should just have to remove the "Email" to support other subscription types.
        # I want to test that out more before opening it up though.
        "Email",
        Use(str.upper),
        Use(lambda x: getattr(sns.SubscriptionProtocol, x)),
    )):  And(
        ## VALUE
        # Break into a list, separating by ANY whitespace:
        str,
        Use(lambda x: x.split()),
    ),
})


def add_sns_subscriptions(context, sns_topic: sns.Topic, subscriptions: dict) -> None:
    """
    Add SNS Subscriptions to an SNS Topic
        (Normally 'subscriptions' is the 'Alert Subscription' block from the config file)
    """
    # subscriptions = {
    #     sns.SubscriptionProtocol.EMAIL: ["email1@gmail.com", "email2@gmail.com"],
    #     sns.SubscriptionProtocol.HTTPS: ["https://example.com", "https://example2.com"],
    #     # ...
    # }
    for protocol, endpoints in subscriptions.items():
        for endpoint in endpoints:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_sns.Subscription.html
            sns.Subscription(
                context,
                f"sns-notify-subscription-{endpoint}",
                protocol=protocol,
                endpoint=endpoint,
                topic=sns_topic,
            )
