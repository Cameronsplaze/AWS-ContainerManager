
"""
Lambda for spinning down the ASG if the container ever throws.
"""

import os
import json
from typing import Any
from functools import cache
from dataclasses import dataclass, asdict

import boto3

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.data_classes import EventBridgeEvent, event_source
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.logging import correlation_paths

logger = Logger()

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
def get_asg_client():
    """ ASG client """
    return boto3.client('autoscaling')

# https://docs.aws.amazon.com/powertools/python/latest/utilities/data_classes/#eventbridge
@event_source(data_class=EventBridgeEvent)
@logger.inject_lambda_context(clear_state=True, correlation_id_path=correlation_paths.EVENT_BRIDGE)
def lambda_handler(event: EventBridgeEvent, context: LambdaContext) -> None: # pylint: disable=unused-argument
    """ Main function of the lambda. """
    try:
        env = get_env_vars()
        logger.append_keys(env_vars=asdict(env), event=event.raw_event)

        asg_client = get_asg_client()

        ## Spin down the instance. The instance-StateChange-hook will do the rest:
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/autoscaling.html#AutoScaling.Client.update_auto_scaling_group
        response = asg_client.update_auto_scaling_group(
            AutoScalingGroupName=env.ASG_NAME,
            DesiredCapacity=0,
        )
        logger.debug("ASG update response", extra={"response": response})
    except Exception:
        logger.exception("Failed to spin down the ASG.")
        raise
    logger.info("Successfully spun down the ASG.")
