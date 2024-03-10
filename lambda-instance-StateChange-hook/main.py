
import os

import boto3


required_vars = ["HOSTED_ZONE_ID", "DOMAIN_NAME", "UNAVAILABLE_IP", "UNAVAILABLE_TTL", "ASG_NAME", "WATCH_INSTANCE_RULE"]
missing_vars = [x for x in required_vars if not os.environ.get(x)]
if any(missing_vars):
    raise RuntimeError(f"Missing environment vars: [{', '.join(missing_vars)}]")

# Boto3 Clients:
#    Can get cached if function is reused, keep clients that are *always* hit here:
route53_client = boto3.client('route53')
events_client = boto3.client('events')

def lambda_handler(event, context) -> None:
    ### Figure out the new IP Address:
    # If the ec2 instance just came up:
    if event["detail-type"] == "EC2 Instance Launch Successful":
        instance_id = event["detail"]["EC2InstanceId"]
        # Client is here since it's only needed if the instance just came up
        #    (And they take a long time to load):
        ec2_client = boto3.client('ec2')
        instance_details = ec2_client.describe_instances(InstanceIds=[instance_id])["Reservations"][0]["Instances"][0]
        # Now you have the new Route53 info:
        new_ip = instance_details["PublicIpAddress"]
        new_ttl = 60
        # Now time to turn everything on! (lambda cron alarms will turn everything off when time.
        #    Doing it there is more stable, and will reset the system if something goes wrong.)
        events_client.enable_rule(Name=os.environ["WATCH_INSTANCE_RULE"])

    # If the ec2 instance just went down:
    elif event["detail-type"] == "EC2 Instance-terminate Lifecycle Action":
        # There's a window where if a instance is coming up as this is hit, this could wipe the
        # ip of the new instance from route53. Normally boto3.client is expensive, but we only
        # care about spin-up time. This is when the system is resetting anyways.
        asg_client = boto3.client('autoscaling')
        asg_info = asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[os.environ["ASG_NAME"]])['AutoScalingGroups'][0]
        for instance in asg_info['Instances']:
            # If there's a instance in ANY of the Pending states, or just finished starting, let IT update the DNS stuff
            if instance['LifecycleState'].startswith("Pending") or  instance['LifecycleState'] == "InService":
                print(f"Instance '{instance['InstanceId']}' is in '{instance['LifecycleState']}', skipping this termination event (triggered by '{event['EC2InstanceId']}')")
                return
        # Route53 info meaning the system is now off-line:
        new_ip = os.environ["UNAVAILABLE_IP"]
        new_ttl = int(os.environ["UNAVAILABLE_TTL"])
        # TODO: Move this to the shutdown lambda when it's finished. The whole system
        #      will be a lot more stable, and also reset itself if something goes wrong.
        events_client.disable_rule(Name=os.environ["WATCH_INSTANCE_RULE"])

    # If the EventBridge filter somehow changed (This should never happen):
    else:
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
