
"""
Lambda for spinning down the ASG if the container ever throws.
"""

import os
import json

from dataclasses import dataclass, asdict

import boto3

# frozen=True: This should never be modified (change cdk inputs instead)
@dataclass(frozen=True)
class EnvVars:
    """ Env vars that the lambda needs. """
    # pylint: disable=invalid-name
    ASG_NAME: str
    # pylint: enable=invalid-name

# Lazy-load the env vars on first use
_env_vars: EnvVars | None = None

def get_env_vars() -> EnvVars:
    """ Lazy-load and validate the environment variables """
    global _env_vars # pylint: disable=global-statement
    if _env_vars is None:
        # Make sure each one is set in the lambda environment:
        missing_vars = [var for var in EnvVars.__annotations__.keys() if var not in os.environ]
        if missing_vars:
            # If there's more than one, flag both of them at once:
            raise RuntimeError(f"Missing environment vars: [{', '.join(missing_vars)}]")
        # Set the validated EnvVars for next call:
        _env_vars = EnvVars(**{k: os.environ[k] for k in EnvVars.__annotations__.keys()})
    return _env_vars


asg_client = boto3.client('autoscaling')

def lambda_handler(event, context):
    """ Main function of the lambda. """
    env = get_env_vars()
    print(json.dumps({"Event": event, "Context": context, "Env": asdict(env)}, default=str))

    ## Spin down the instance. The instance-StateChange-hook will do the rest:
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/autoscaling.html#AutoScaling.Client.update_auto_scaling_group
    asg_client.update_auto_scaling_group(
        AutoScalingGroupName=env.ASG_NAME,
        DesiredCapacity=0,
    )
