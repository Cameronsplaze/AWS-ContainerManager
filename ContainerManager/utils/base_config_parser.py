"""
Base Config Parser

The docs for schema is at: https://github.com/keleshev/schema
"""
from schema import Schema, And, Use, Optional

from .sns_subscriptions import sns_schema


###################
### Base Config ###
###################
def base_config_schema():
    """ Base config schema for the base stack. """
    return Schema({
        "Vpc": {
            Optional("MaxAZs", default=1): int,
        },
        "Domain": {
            "Name": And(str, Use(str.lower)),
            "HostedZoneId": str,
        },
        Optional("AlertSubscription", default={}): {
            Optional("Email"): str,
        },
        Optional("AlertSubscription", default={}): sns_schema,
    })
