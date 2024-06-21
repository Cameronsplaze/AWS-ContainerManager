
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
    "WATCH_INSTANCE_RULE",
    "ECS_CLUSTER_NAME",
    "ECS_SERVICE_NAME",
]
missing_vars = [x for x in required_vars if not os.environ.get(x)]
if any(missing_vars):
    raise RuntimeError(f"Missing environment vars: [{', '.join(missing_vars)}]")

# Boto3 Clients:
#    Can get cached if function is reused, keep clients that are used on spin-UP here:
route53_client = boto3.client('route53') # Used for updating DNS record
events_client = boto3.client('events')   # Used for enabling/disabling the watchdog lambda
ecs_client = boto3.client('ecs')         # Used for updating the ECS service
ec2_client = boto3.client('ec2')         # Used for getting the new instance's IP

def lambda_handler(event: dict, context: dict) -> None:
    print(json.dumps({"Event": event, "Context": context}, default=str))

    ### If the ec2 instance just FINISHED coming up:
    if event["detail-type"] == "EC2 Instance Launch Successful":
        try:
            update_system(spin_up=True, event=event)
        finally:
            # We're doing this last, since it's not required for a user to connect (Get them in ASAP)
            # BUT we want to make sure this ALWAYS happens! If something goes wrong, this'll grantee
            # the instance will eventually spin down.
            events_client.enable_rule(Name=os.environ["WATCH_INSTANCE_RULE"])

    ### If the ec2 instance just STARTED to go down:
    elif event["detail-type"] == "EC2 Instance-terminate Lifecycle Action":
        try:
            ### Safety Check - If another instance is spinning up, just quit:
            exit_if_asg_instance_coming_up(asg_name=event["detail"]["AutoScalingGroupName"])
            # Now just update the system like normal:
            update_system(spin_up=False, event=event)
        finally:
            events_client.disable_rule(Name=os.environ["WATCH_INSTANCE_RULE"])

    ### If the EventBridge filter somehow changed (This should never happen):
    else:
        raise RuntimeError(f"Unknown event type: '{event['detail-type']}'. Did you mess with the EventBridge Rule??")



def update_system(spin_up: bool, event: dict) -> None:
    # Update the ECS service first, it'll take the longest to turn on:
    update_ecs_service(desired_count=1 if spin_up else 0)

    # Update the DNS to the new public IP:
    if spin_up:
        new_ip = get_instance_ip(instance_id=event["detail"]["EC2InstanceId"])
    else:
        new_ip = os.environ["UNAVAILABLE_IP"]
    update_dns_zone(new_ip)


def get_instance_ip(instance_id: str) -> str:
    # Since you're supplying an ID, there should always be exactly one:
    instance_details = ec2_client.describe_instances(InstanceIds=[instance_id])["Reservations"][0]["Instances"][0]
    # Now you have the new ip for the instance:
    return instance_details["PublicIpAddress"]


def update_dns_zone(new_ip: str) -> None:
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


def update_ecs_service(desired_count: int) -> None:
    print(f"Spinning {'up' if desired_count else 'down'} ecs service ({desired_count=})")
    ## Spin up the task on the new instance:
    ecs_client.update_service(
        cluster=os.environ["ECS_CLUSTER_NAME"],
        service=os.environ["ECS_SERVICE_NAME"],
        desiredCount=desired_count,
    )


def exit_if_asg_instance_coming_up(asg_name: str) -> None:
    # - There's a window where if a instance is coming up as another spins down, it could wipe the
    # ip of the new instance from route53. This is a safety check to make sure that doesn't happen.
    # - Normally initializing boto3.client is expensive, but we only
    # care about spin-*UP* time. This only runs when system is shutting down.
    asg_client = boto3.client('autoscaling')
    # With using asg_name, we guarantee there's only one output:
    asg_info = asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])['AutoScalingGroups'][0]
    for instance in asg_info['Instances']:
        # If there's a instance in ANY of the Pending states, or just finished starting, let IT update the DNS stuff.
        # We don't want to step over it with this instance going down.
        if instance['LifecycleState'].startswith("Pending") or  instance['LifecycleState'] == "InService":
            print(f"Instance '{instance['InstanceId']}' is in '{instance['LifecycleState']}', skipping this termination event.")
            sys.exit()

