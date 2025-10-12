
"""
Lambda code for starting and stopping the management logic
whenever the ASG state changes (instance starts or stops).
"""

import os
import sys
import json

import boto3

required_vars = [
    "HOSTED_ZONE_ID",
    "DOMAIN_NAME",
    "UNAVAILABLE_IP",
    "DNS_TTL",
    "RECORD_TYPE",
]
missing_vars = [x for x in required_vars if not os.environ.get(x)]
if any(missing_vars):
    raise RuntimeError(f"Missing environment vars: [{', '.join(missing_vars)}]")

# Boto3 Clients:
#    Can get cached if function is reused, keep clients that are used on spin-UP here:
route53_client = boto3.client('route53') # Used for updating DNS record
ec2_client = boto3.client('ec2')         # Used for getting the new instance's IP
# Optional Client (Only hit when the server's spinning DOWN):
asg_client = None  # Used for updating DNS record
def _get_asg_client():
    """ Lazy-load the asg client, only if needed """
    global asg_client # pylint: disable=global-statement
    if asg_client is None:
        asg_client = boto3.client('autoscaling')
    return asg_client


def lambda_handler(event: dict, context: dict) -> None:
    """
    Main function of the lambda.
    """
    print(json.dumps({"Event": event, "Context": context}, default=str))

    # If the ec2 instance just FINISHED coming up:
    if event["detail-type"] == "EC2 Instance Launch Successful":
        new_ip = get_public_ip(instance_id=event["detail"]["EC2InstanceId"])
    # If the ec2 instance just STARTED to go down:
    elif event["detail-type"] == "EC2 Instance-terminate Lifecycle Action":
        ### Safety Check - If another instance is spinning up, just quit:
        exit_if_asg_instance_coming_up(asg_name=event["detail"]["AutoScalingGroupName"])
        # Now just update DNS like normal:
        new_ip = os.environ["UNAVAILABLE_IP"]
    # If the EventBridge filter somehow changed (This should never happen):
    else:
        raise RuntimeError(f"Unknown event type: '{event['detail-type']}'. Did you mess with the EventBridge Rule??")
    ### Update the DNS record with the new IP:
    update_dns_zone(new_ip)

def get_public_ip(instance_id: str) -> str:
    """ Get the instance's public IP """
    # Since you're supplying an ID, there should always be exactly one:
    instance_details = ec2_client.describe_instances(InstanceIds=[instance_id])["Reservations"][0]["Instances"][0]
    print(f"Instance details: {json.dumps(instance_details, indent=4, default=str)}")
    return instance_details["PublicIpAddress"]


def update_dns_zone(new_ip: str) -> None:
    """ Update the DNS record with the new IP """
    print(f"Changing to new IP: {new_ip}")
    ### Update the record with the new IP:
    route53_client.change_resource_record_sets(
        HostedZoneId=os.environ['HOSTED_ZONE_ID'],
        ChangeBatch={
            'Changes': [{
                'Action': 'UPSERT',
                'ResourceRecordSet': {
                    'Name': os.environ['DOMAIN_NAME'],
                    'Type': os.environ['RECORD_TYPE'],
                    'ResourceRecords': [{'Value': new_ip}],
                    'TTL': int(os.environ['DNS_TTL']),
                }
            }]
        }
    )

def exit_if_asg_instance_coming_up(asg_name: str) -> None:
    """
    SAFEGUARD: Exit if another instance is coming up in the ASG
    
    There's a window where if a instance is coming up as another spins down, the latter could wipe the
    ip of the new instance from route53. This is a safety check to make sure that doesn't happen.
    """
    # asg_client: Normally initializing boto3.client is expensive and this should be global, BUT we only
    # care about spin-*UP* time. This only runs when system is shutting *down*.
    asg_client = _get_asg_client() # pylint: disable=redefined-outer-name
    # With using asg_name, we guarantee there's only one output:
    asg_info = asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])['AutoScalingGroups'][0]
    for instance in asg_info['Instances']:
        # If there's a instance in ANY of the Pending states, or just finished starting, let IT update the DNS stuff.
        # We don't want to step over it with this instance going down.
        if instance['LifecycleState'].startswith("Pending") or  instance['LifecycleState'] == "InService":
            msg = f"Instance '{instance['InstanceId']}' is in '{instance['LifecycleState']}', skipping this termination event."
            print(msg)
            sys.exit(msg)
