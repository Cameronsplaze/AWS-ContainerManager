
"""
Lambda code for starting and stopping the management logic
whenever the ASG state changes (instance starts or stops).
"""

import os
import sys
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
    HOSTED_ZONE_ID: str
    DOMAIN_NAME: str
    UNAVAILABLE_IP: str
    DNS_TTL: int
    RECORD_TYPE: str
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
def get_route53_client():
    """ Used for updating the DNS record """
    return boto3.client('route53')

@cache
def get_ec2_client():
    """ Used for getting the new instance's IP """
    return boto3.client('ec2')

@cache
def get_asg_client():
    """ Used for checking ASG instance states """
    return boto3.client('autoscaling')


def get_public_ip(instance_id: str) -> str:
    """ Get the instance's public IP """
    # Since you're supplying an ID, there should always be exactly one:
    ec2_client = get_ec2_client()
    instance_details = ec2_client.describe_instances(InstanceIds=[instance_id])["Reservations"][0]["Instances"][0]
    return instance_details["PublicIpAddress"]


def update_dns_zone(new_ip: str) -> None:
    """ Update the DNS record with the new IP """
    env = get_env_vars()

    ### Update the record with the new IP:
    route53_client = get_route53_client()
    response = route53_client.change_resource_record_sets(
        HostedZoneId=env.HOSTED_ZONE_ID,
        ChangeBatch={
            'Changes': [{
                'Action': 'UPSERT',
                'ResourceRecordSet': {
                    'Name': env.DOMAIN_NAME,
                    'Type': env.RECORD_TYPE,
                    'ResourceRecords': [{'Value': new_ip}],
                    'TTL': env.DNS_TTL,
                }
            }]
        }
    )
    logger.debug("Route53 update response", extra={"response": response})

def check_if_asg_instance_coming_up(asg_name: str) -> bool:
    """
    SAFEGUARD: Exit if another instance is coming up in the ASG
    
    There's a window where if a instance is coming up as another spins down, the latter could wipe the
    ip of the new instance from route53. This is a safety check to make sure that doesn't happen.
    """
    # asg_client: Normally initializing boto3.client is expensive and this should be global, BUT we only
    # care about spin-*UP* time. This only runs when system is shutting *down*.
    asg_client = get_asg_client() # pylint: disable=redefined-outer-name
    # With using asg_name, we guarantee there's only one output:
    asg_info = asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])['AutoScalingGroups'][0]
    for instance in asg_info['Instances']:
        # If there's a instance in ANY of the Pending states, or just finished starting, let IT update the DNS stuff.
        # We don't want to step over it with this instance going down.
        if instance['LifecycleState'].startswith("Pending") or  instance['LifecycleState'] == "InService":
            logger.warning(f"Instance '{instance['InstanceId']}' is in '{instance['LifecycleState']}', skipping this termination event.")
            return True
    return False

# https://docs.aws.amazon.com/powertools/python/latest/utilities/data_classes/#eventbridge
@event_source(data_class=EventBridgeEvent)
@logger.inject_lambda_context(clear_state=True, correlation_id_path=correlation_paths.EVENT_BRIDGE)
def lambda_handler(event: EventBridgeEvent, context: LambdaContext) -> None: # pylint: disable=unused-argument
    """ Main function of the lambda. """
    try:
        env = get_env_vars()
        logger.append_keys(env_vars=asdict(env), event=event.raw_event)

        # If the ec2 instance just FINISHED coming up:
        if event["detail-type"] == "EC2 Instance Launch Successful":
            new_ip = get_public_ip(instance_id=event["detail"]["EC2InstanceId"])
        # If the ec2 instance just STARTED to go down:
        elif event["detail-type"] == "EC2 Instance-terminate Lifecycle Action":
            # Safety Check - If another instance is spinning up, just quit:
            if check_if_asg_instance_coming_up(asg_name=event["detail"]["AutoScalingGroupName"]):
                return
            # Now just update DNS like normal:
            new_ip = env.UNAVAILABLE_IP
        # If the EventBridge filter somehow changed (This should never happen):
        else:
            raise RuntimeError(f"Unknown event type: '{event['detail-type']}'. Did you mess with the EventBridge Rule??")

        ### Update the DNS record with the new IP:
        logger.append_keys(new_ip=new_ip)
        update_dns_zone(new_ip)
    except Exception:
        logger.exception("Failed to manage the ec2 instance.")
        raise
    logger.info("Successfully managed the ec2 instance.")
