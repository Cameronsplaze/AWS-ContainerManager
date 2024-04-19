
import os
import sys
import json

import boto3

required_vars = [
    "HOSTED_ZONE_ID",
    "DOMAIN_NAME",
    "UNAVAILABLE_IP",
    "UNAVAILABLE_TTL",
    "RECORD_TYPE",
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
events_client = boto3.client('events')
ecs_client = boto3.client('ecs')

def lambda_handler(event, context) -> None:
    print(json.dumps({"Event": event, "Context": context}, default=str))
    # If the ec2 instance just FINISHED coming up:
    if event["detail-type"] == "EC2 Instance Launch Successful":
        ### Start ECS First, it'll take the longest:
        update_ecs_service(desired_count=1)
        ### Update DNS to the new public IP:
        instance_id = event["detail"]["EC2InstanceId"]
        new_ip, new_ttl = get_ip_info(instance_id)
        update_dns_zone(new_ip, new_ttl)
        ### Start the WatchDog Lambda:
        # (Doing this last since it's not required for a user to connect)
        events_client.enable_rule(Name=os.environ["WATCH_INSTANCE_RULE"])

    # If the ec2 instance just STARTED to go down:
    elif event["detail-type"] == "EC2 Instance-terminate Lifecycle Action":
        ### Check if another instance is spinning up, so you can just quit:
        asg_name = event["detail"]["AutoScalingGroupName"]
        check_asg_if_pending(asg_name)
        ### Update DNS with the unavailable info:
        new_ip = os.environ["UNAVAILABLE_IP"]
        new_ttl = int(os.environ["UNAVAILABLE_TTL"])
        update_dns_zone(new_ip, new_ttl)
        ### Stop the WatchDog Lambda:
        events_client.disable_rule(Name=os.environ["WATCH_INSTANCE_RULE"])
        ### Spin down the task:
        update_ecs_service(desired_count=0)


    # If the EventBridge filter somehow changed (This should never happen):
    else:
        print({"Event": event, "Context": context})
        raise RuntimeError(f"Unknown event type: '{event['detail-type']}'. Did you mess with the EventBridge Rule??")

def get_ip_info(instance_id: str) -> tuple[str, int]:
        ## Get the new IP from the instance:
        ec2_client = boto3.client('ec2')
        instance_details = ec2_client.describe_instances(InstanceIds=[instance_id])["Reservations"][0]["Instances"][0]
        # Now you have the new Route53 info:
        new_ip = instance_details["PublicIpAddress"]
        new_ttl = 60
        return new_ip, new_ttl

def update_dns_zone(new_ip: str, new_ttl: int) -> None:
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
                    'TTL': new_ttl,
                    'ResourceRecords': [{'Value': new_ip}]
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
    ## I don't think we ever need to wait for this to finish? But just in case:
    # ecs_service_waiter = ecs_client.get_waiter('services_stable')
    # ecs_service_waiter.wait(
    #     cluster=os.environ["ECS_CLUSTER_NAME"],
    #     services=[os.environ["ECS_SERVICE_NAME"]],
    #     WaiterConfig={
    #         "Delay": 1,
    #         "MaxAttempts": 120,
    #     },
    # )

def check_asg_if_pending(asg_name) -> None:
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

