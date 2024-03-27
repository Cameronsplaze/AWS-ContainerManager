
import os
import sys
import json

import boto3

required_vars = [
    "HOSTED_ZONE_ID",
    "DOMAIN_NAME",
    "UNAVAILABLE_IP",
    "UNAVAILABLE_TTL",
    "WATCH_INSTANCE_RULE",
    "ECS_CLUSTER_NAME",
    "ECS_SERVICE_NAME",
]
missing_vars = [x for x in required_vars if not os.environ.get(x)]
if any(missing_vars):
    raise RuntimeError(f"Missing environment vars: [{', '.join(missing_vars)}]")

# Boto3 Clients:
#    Can get cached if function is reused, keep clients that are *always* hit here:
route53_client = boto3.client('route53')

def lambda_handler(event, context) -> None:
    print(json.dumps({"Event": event, "Context": context}, default=str))
    # If the ec2 instance just came up:
    if event["detail-type"] == "EC2 Instance Launch Successful":
        instance_id = event["detail"]["EC2InstanceId"]
        new_ip, new_ttl = spin_up_system(instance_id)

    # If the ec2 instance just went down:
    elif event["detail-type"] == "EC2 Instance-terminate Lifecycle Action":
        asg_name = event["detail"]["AutoScalingGroupName"]
        new_ip, new_ttl = spin_down_system(asg_name)

    # If the EventBridge filter somehow changed (This should never happen):
    else:
        print({"Event": event, "Context": context})
        raise RuntimeError(f"Unknown event type: '{event['detail-type']}'. Did you mess with the EventBridge Rule??")

    print(f"Changing to new IP: {new_ip}")

    ### Update the record with the new IP:
    route53_client.change_resource_record_sets(
        HostedZoneId=os.environ['HOSTED_ZONE_ID'],
        ChangeBatch={
            'Changes': [{
                'Action': 'UPSERT',
                'ResourceRecordSet': {
                    'Name': os.environ['DOMAIN_NAME'],
                    'Type': 'A',
                    'TTL': new_ttl,
                    'ResourceRecords': [{'Value': new_ip}]
                }
            }]
        }
    )

def spin_up_system(instance_id):
    try:
        ecs_client = boto3.client('ecs')
        ## Spin up the task on the new instance:
        ecs_client.update_service(
            cluster=os.environ["ECS_CLUSTER_NAME"],
            service=os.environ["ECS_SERVICE_NAME"],
            desiredCount=1,
        )
        ### TODO: Should we wait for it to finish? If we don't,
        ## it'll update the DNS faster, and maybe they finish at
        ## the same time?
        # ecs_service_waiter = ecs_client.get_waiter('services_stable')
        # ecs_service_waiter.wait(
        #     cluster=os.environ["ECS_CLUSTER_NAME"],
        #     services=[os.environ["ECS_SERVICE_NAME"]],
        #     WaiterConfig={
        #         "Delay": 1,
        #         "MaxAttempts": 120,
        #     },
        # )
        ## Get the new IP from the instance:
        ec2_client = boto3.client('ec2')
        instance_details = ec2_client.describe_instances(InstanceIds=[instance_id])["Reservations"][0]["Instances"][0]
        # Now you have the new Route53 info:
        new_ip = instance_details["PublicIpAddress"]
        new_ttl = 60
    finally:
        # If this rule ever doesn't start, you're left with an instance without
        # anything watching it. It'll never turn off, and you'll be charged a LOT.
        # We also want this to run last, so it's here:
        events_client = boto3.client('events')
        events_client.enable_rule(Name=os.environ["WATCH_INSTANCE_RULE"])
    return new_ip, new_ttl

def spin_down_system(asg_name):
    # There's a window where if a instance is coming up as this is hit, this could wipe the
    # ip of the new instance from route53. Normally boto3.client is expensive, but we only
    # care about spin-up time. This is when the system is resetting anyways.
    asg_client = boto3.client('autoscaling')
    asg_info = asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])['AutoScalingGroups'][0]
    for instance in asg_info['Instances']:
        # If there's a instance in ANY of the Pending states, or just finished starting, let IT update the DNS stuff
        if instance['LifecycleState'].startswith("Pending") or  instance['LifecycleState'] == "InService":
            print(f"Instance '{instance['InstanceId']}' is in '{instance['LifecycleState']}', skipping this termination event.")
            sys.exit()
    # Route53 info - meaning the system is now off-line:
    new_ip = os.environ["UNAVAILABLE_IP"]
    new_ttl = int(os.environ["UNAVAILABLE_TTL"])
    return new_ip, new_ttl
