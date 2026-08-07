"""
Leaf Config Parser

The docs for schema is at: https://github.com/keleshev/schema
"""
import ipaddress
from functools import cache

from schema import Schema, And, Or, Use, Optional

import boto3
from aws_cdk import (
    Duration,
    aws_ecs as ecs,
)

from .sns_subscriptions import sns_schema
from .maturity import Maturity

@cache
def get_ec2_client():
    """ Just used to discribe the instance types """
    return boto3.client('ec2')

### You have to keep Schema's separate, when you need an Optional dict of an Optional dict.
# (AKA with {"a": {"b": "c"}}, if you declare "a" as optional, the "b" and "c" dict won't get
# created. It'd be an empty dict instead. This below is to stop copy-pasting it in two places.
# (The default=*, and the parser itself).
leaf_instanceLeftUp_config = Schema({ # pylint: disable=invalid-name
    # DurationHours: Optional, returns a cdk Duration in hours.
    Optional("DurationHours",
        default=Duration.hours(8),
    ): And(int, Use(Duration.hours)),
    Optional("ShouldStop", default=False): bool,
})
leaf_instanceLeftUp_defaults = leaf_instanceLeftUp_config.validate({})

leaf_dashboard_config = Schema({
    Optional("Enabled", default=True): bool,
    Optional("IntervalMinutes",
        default=Duration.minutes(30),
    ): And(int, Use(Duration.minutes)),
    Optional("ShowContainerLogTimestamp", default=True): bool,
})
leaf_dashboard_defaults = leaf_dashboard_config.validate({})

###################
### Leaf Config ###
###################
def leaf_config_schema(maturity: Maturity) -> Schema:
    """ Leaf config schema for the leaf stack. """
    return Schema({
        "Ec2": And(
            {
                "InstanceType": Use(str.lower),
                # List of CIDR's allowed to SSH into the instance
                # TODO: Doc this. Including setting it to an empty list to disable.
                Optional("SshCidrAllowed", default=["0.0.0.0/0"]): [
                    Use(lambda cidr: str(ipaddress.ip_network(cidr, strict=False))),
                ],
            },
            ## Cast the InstanceType to the boto3 response with ALL it's info:
            # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2/client/describe_instance_types.html#EC2.Client.describe_instance_types
            # (Keep "SshCidrAllowed" around too, it doesn't come from this boto3 call):
            Use(lambda info: get_ec2_client().describe_instance_types(
                InstanceTypes=[info["InstanceType"]])["InstanceTypes"][0] | {
                    "SshCidrAllowed": info["SshCidrAllowed"],
                },
            ),
            # Make sure we have at LEAST 2 GB for Host, and 1 GB for guest:
            lambda instance_info: instance_info["MemoryInfo"]["SizeInMiB"] >= 3*1024, # # 3 GB
            # Combine any other keys into the Ec2 Config:
            Use(lambda instance_info: instance_info | {
                # Add a "GpuExists" flag, so downstream code doesn't need to re-check "GpuInfo" itself:
                "GpuExists": bool("GpuInfo" in instance_info and instance_info["GpuInfo"]["Gpus"] > 0),
                #
            }),
        ),
        "Container": {
            "Image": Use(str.lower),
            "Ports": [
                And(
                    # Cast the dict types to what you want:
                    {Use(str.upper): Use(int)},
                    # Assert the ONE key is either TCP or UDP:
                    {Or("TCP", "UDP", only_one=True): int},
                    # Cast it to an ecs port mapping:
                    Use(lambda info: ecs.PortMapping(
                        container_port=list(info.values())[0],
                        host_port=list(info.values())[0],
                        protocol=getattr(ecs.Protocol, list(info.keys())[0]),
                    )),
                ),
            ],
            # Key: Optional, but defaults value to empty dict if not declared:
            # Value: Either a empty dict, or a dict of strings (that casts all values to string).
            #        Make bools all lowercase. Some containers are case-insensitive, others expect all lower.
            Optional("Environment", default={}): Or({Use(str): Use(
                # All values must be strings. If it's a bool, also make it all-lowercase:
                lambda val: str(val).lower() if isinstance(val, bool) else str(val))},
                # You're allowed to set an empty dict here:
                {},
            ),
        },
        Optional("Volume", default={}): {
            Optional("EnableBackups", default=bool(maturity == Maturity.PROD)): bool,
            Optional("KeepOnDelete", default=bool(maturity == Maturity.PROD)): bool,
            # List of Path Configs to save:
            "Paths": [{
                "Path": str,
                Optional("ReadOnly", default=False): bool,
            }],
        },
        "Watchdog": {
            "Threshold": int,
            # MinutesWithoutConnections: Optional, returns a cdk Duration in minutes.
            Optional("MinutesWithoutConnections",
                default=Duration.minutes(7),
            ): And(int, Use(Duration.minutes)),
            Optional("InstanceLeftUp", default=leaf_instanceLeftUp_defaults): leaf_instanceLeftUp_config,
        },
        Optional("AlertSubscription", default={}): sns_schema,
        Optional("Dashboard", default=leaf_dashboard_defaults): leaf_dashboard_config,
    })
