
"""
Lambda for spinning down the ASG if the container ever throws.
"""

import os
import json
from functools import cache
from dataclasses import dataclass, asdict

import boto3

# frozen=True: This should never be modified (change cdk inputs instead)
@dataclass(frozen=True)
class EnvVars:
    """ Env vars that the lambda needs. """
    # pylint: disable=invalid-name
    ASG_NAME: str
    # pylint: enable=invalid-name

@cache
def get_env_vars() -> EnvVars:
    """ Lazy-load and Validate the environment variables """
    # EnvVars will naturally error with ALL the missing env-vars on creation:
    return EnvVars(**{
        # DON'T use getenv. We don't want the key to exist if it's missing.
        k: os.environ[k] for k in EnvVars.__annotations__.keys() if k in os.environ
    })

## Boto3 Clients:
# ALWAYS use @cache for clients. Even if they're always called, it helps
# them not exist until moto is setup inside of the test suite.
@cache
def get_asg_client():
    """ ASG client """
    return boto3.client('autoscaling')

def lambda_handler(event, context):
    """ Main function of the lambda. """
    env = get_env_vars()
    print(json.dumps({"Event": event, "Context": context, "Env": asdict(env)}, default=str))
    asg_client = get_asg_client()

    ## Spin down the instance. The instance-StateChange-hook will do the rest:
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/autoscaling.html#AutoScaling.Client.update_auto_scaling_group
    asg_client.update_auto_scaling_group(
        AutoScalingGroupName=env.ASG_NAME,
        DesiredCapacity=0,
    )
