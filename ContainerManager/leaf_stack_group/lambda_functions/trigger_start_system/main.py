
"""
Lambda code for starting the system when someone tries to connect.
"""

import os
import json
from typing import Any
from functools import cache
from dataclasses import dataclass, asdict

import boto3

# frozen=True: This should never be modified (change cdk inputs instead)
@dataclass(frozen=True)
class EnvVars:
    """ Env vars that the lambda needs. """
    # pylint: disable=invalid-name
    ASG_NAME: str
    MANAGER_STACK_REGION: str
    ALLOWED_CIDR_IPS: list[str]
    # For not letting the system spin down if someone is trying to connect:
    METRIC_NAMESPACE: str
    METRIC_NAME: str
    METRIC_THRESHOLD: int
    METRIC_UNIT: str
    METRIC_DIMENSIONS: dict[str, str]
    # pylint: enable=invalid-name

@cache
# TODO: Update the other functions with this
def get_env_vars() -> EnvVars:
    """ Lazy-load and Validate the environment variables """
    env_vars: dict[str, Any] = {
        # If it's supposed to be a string already, DON'T json.loads it:
        k: os.environ[k] if var_type is str else json.loads(os.environ[k])
        for k, var_type in EnvVars.__annotations__.items()
        if k in os.environ
    }
    # EnvVars will naturally error with ALL the missing env-vars on creation:
    return EnvVars(**env_vars)

## Boto3 Clients:
# ALWAYS use @cache for clients. Even if they're always called, it helps
# them not exist until moto is setup inside of the test suite.
@cache
def get_cloudwatch_client():
    """ Used for putting metric data """
    env = get_env_vars()
    return boto3.client('cloudwatch', region_name=env.MANAGER_STACK_REGION)

@cache
def get_asg_client():
    """ Used for updating the ASG desired capacity """
    env = get_env_vars()
    return boto3.client('autoscaling', region_name=env.MANAGER_STACK_REGION)


def lambda_handler(event, context):
    """ Main function of the lambda. """
    env = get_env_vars()

    # TODO HERE: Convert event to dict (log the human-readable version)

    print(json.dumps({"Event": event, "Context": context, "Env": asdict(env)}, default=str))

    # TODO HERE: Actually parse out the IP and compare it to the allowed list.

    # Change the dimension map to the format boto3 cloudwatch wants:
    dimension_map = [{"Name": k, "Value": v} for k, v in env.METRIC_DIMENSIONS.items()]
    # Pushing to this metric will stop the Watchdog alarm from spinning down the instance.
    cloudwatch_client = get_cloudwatch_client()
    cloudwatch_client.put_metric_data(
        Namespace=env.METRIC_NAMESPACE,
        MetricData=[{
            'MetricName': env.METRIC_NAME,
            'Dimensions': dimension_map,
            'Unit': env.METRIC_UNIT,
            'Value': env.METRIC_THRESHOLD,
        }],
    )

    ## Spin up the instance. The instance-StateChange-hook will do the rest:
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/autoscaling.html#AutoScaling.Client.update_auto_scaling_group
    asg_client = get_asg_client()
    asg_client.update_auto_scaling_group(
        AutoScalingGroupName=env.ASG_NAME,
        DesiredCapacity=1,
    )
