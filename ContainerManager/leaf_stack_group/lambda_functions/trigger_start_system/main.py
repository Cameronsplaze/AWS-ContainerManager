
"""
Lambda code for starting the system when someone tries to connect.
"""

import os
import json
import ipaddress
from typing import Any
from functools import cache
from dataclasses import dataclass, asdict

import boto3

from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.data_classes import CloudWatchLogsEvent, event_source
from aws_lambda_powertools.utilities.data_classes.cloud_watch_logs_event import CloudWatchLogsDecodedData
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger()

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

def is_client_allowed(client_subnets: list[str]) -> bool:
    """If ANY of the client_subnets overlaps ANY of the ALLOWED_CIDR_IPS. 

    THIS IS JUST A COST-SAVER (And to lessen start-up email spam).
    The real security is on the EC2 Security Group.
        1) The client IP is optional (and "-" when not sent)
        2) They only give the IP range, so there's 255 IP's *minimum* that could match.
    """
    env = get_env_vars()
    # The resolver doesn't always send an ip (like cloudflare). Just spin up the instance
    if "-" in client_subnets:
        return True
    # Check against the partial cidr they send us (they don't send the full IP).
    return any(
        ipaddress.ip_network(subnet).overlaps(ipaddress.ip_network(cidr))
        for subnet in client_subnets
        for cidr in env.ALLOWED_CIDR_IPS
    )

def push_metric_connection() -> None:
    """Push a metric to cloudwatch. This is used to keep the system from spinning down."""
    ## YOU CANNOT USE POWERTOOLS METRICS HERE: It does not have any cross-region
    #    support, since it uses EMF JSON, and not put_metric_data behind the scenes.
    env = get_env_vars()
    cloudwatch_client = get_cloudwatch_client()
    # Change the dimension map to the format boto3 cloudwatch wants:
    dimension_map = [{"Name": k, "Value": v} for k, v in env.METRIC_DIMENSIONS.items()]
    response =cloudwatch_client.put_metric_data(
        Namespace=env.METRIC_NAMESPACE,
        MetricData=[{
            'MetricName': env.METRIC_NAME,
            'Dimensions': dimension_map,
            'Unit': env.METRIC_UNIT,
            'Value': env.METRIC_THRESHOLD,
        }],
    )
    logger.debug("Pushed metric to cloudwatch.", extra={"response": response})

def start_system() -> None:
    """Spin up the system. The instance-StateChange-hook will do the rest."""
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/autoscaling.html#AutoScaling.Client.update_auto_scaling_group
    env = get_env_vars()
    asg_client = get_asg_client()
    response = asg_client.update_auto_scaling_group(
        AutoScalingGroupName=env.ASG_NAME,
        DesiredCapacity=1,
    )
    logger.debug("Updated ASG desired capacity to 1.", extra={"response": response})

## Decompress CloudWatch Logs:
# https://docs.aws.amazon.com/powertools/python/latest/utilities/data_classes/#cloudwatch-logs
@event_source(data_class=CloudWatchLogsEvent)
@logger.inject_lambda_context(clear_state=True, log_event=False)
def lambda_handler(event: CloudWatchLogsEvent, context: LambdaContext): # pylint: disable=unused-argument
    """ Main function of the lambda. """
    try:
        env = get_env_vars()
        logger.append_keys(env_vars=asdict(env))

        decompressed_log: CloudWatchLogsDecodedData = event.parse_logs_data()

        ## Fields Are:
        # [version, timestamp, hosted_zone_id, domain_name, dns_record_type,
        #   response_code, protocol, edge_location, dns_resolver_ip, client_subnet]
        client_subnets = [x.message.split()[9] for x in decompressed_log.log_events]
        # Append to the rest of the messages this run:
        logger.append_keys(client_subnets=client_subnets)
        if not is_client_allowed(client_subnets):
            logger.warning("No client subnet overlaps ALLOWED_CIDR_IPS, NOT starting the system.")
            return

        push_metric_connection()
        start_system()
    except Exception:
        logger.exception("Failed to start the system.")  # Includes all the keys we've added
        raise

    logger.info("Started the system.")
