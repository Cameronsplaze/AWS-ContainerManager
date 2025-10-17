
"""
Lambda code for starting the system when someone tries to connect.
"""

import os
import json

from dataclasses import dataclass, asdict

import boto3
from botocore.config import Config

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

# Boto3 Clients:
config = Config(region_name=os.environ["MANAGER_STACK_REGION"])
cloudwatch_client = boto3.client('cloudwatch', config=config)
asg_client = boto3.client('autoscaling', config=config)

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
    asg_client.update_auto_scaling_group(
        AutoScalingGroupName=env.ASG_NAME,
        DesiredCapacity=1,
    )
