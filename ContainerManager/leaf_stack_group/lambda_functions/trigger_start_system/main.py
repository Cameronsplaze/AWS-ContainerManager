
"""
Lambda code for starting the system when someone tries to connect.
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
    MANAGER_STACK_REGION: str
    # For not letting the system spin down if someone is trying to connect:
    METRIC_NAMESPACE: str
    METRIC_NAME: str
    METRIC_THRESHOLD: str
    METRIC_UNIT: str
    METRIC_DIMENSIONS: str
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
    print(json.dumps({"Event": event, "Context": context, "Env": asdict(env)}, default=str))

    ### Let the metric know someone is trying to connect, to stop it
    ### from alarming and spinning down the system:
    ###   (Also if the system is in alarm, this resets it so it can spin down again)
    dimensions_input = json.loads(env.METRIC_DIMENSIONS)
    # Change it to the format boto3 cloudwatch wants:
    dimension_map = [{"Name": k, "Value": v} for k, v in dimensions_input.items()]
    cloudwatch_client = get_cloudwatch_client()
    cloudwatch_client.put_metric_data(
        Namespace=env.METRIC_NAMESPACE,
        MetricData=[{
            'MetricName': env.METRIC_NAME,
            'Dimensions': dimension_map,
            'Unit': env.METRIC_UNIT,
            # One greater than the threshold, to make sure the alarm doesn't error:
            'Value': 1+int(env.METRIC_THRESHOLD),
        }],
    )

    ## Spin up the instance. The instance-StateChange-hook will do the rest:
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/autoscaling.html#AutoScaling.Client.update_auto_scaling_group
    asg_client = get_asg_client()
    asg_client.update_auto_scaling_group(
        AutoScalingGroupName=env.ASG_NAME,
        DesiredCapacity=1,
    )
