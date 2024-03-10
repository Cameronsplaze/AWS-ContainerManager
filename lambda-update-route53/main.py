
import os

import boto3


required_vars = ["HOSTED_ZONE_ID", "DOMAIN_NAME", "UNAVAILABLE_IP", "UNAVAILABLE_TTL"]
missing_vars = [x for x in required_vars if not os.environ.get(x)]
if any(missing_vars):
    raise RuntimeError(f"Missing environment vars: [{', '.join(missing_vars)}]")

route53_client = boto3.client('route53')

def lambda_handler(event, context):
    ### Figure out the new IP Address:
    # If the ec2 instance just came up:
    if event["detail-type"] == "EC2 Instance Launch Successful":
        instance_id = event["detail"]["EC2InstanceId"]
        # Client is here since it's only needed if the instance just came up
        #    (And they take a long time to load):
        ec2_client = boto3.client('ec2')
        # This shouldn't keyerror since the event just launched, and you're only asking for one instance:
        instance_details = ec2_client.describe_instances(InstanceIds=[instance_id])["Reservations"][0]["Instances"][0]
        new_ip = instance_details["PublicIpAddress"]
        new_ttl = 60

    # If the ec2 instance just went down:
    elif event["detail-type"] == "EC2 Instance Terminate Successful":
        new_ip = os.environ["UNAVAILABLE_IP"]
        new_ttl = int(os.environ["UNAVAILABLE_TTL"])
    # If the EventBridge filter somehow changed:
    else:
        raise RuntimeError(f"Unknown event type: {event['detail-type']}. Did you mess with the EventBridge Rule?")
    print(f"Changing to new IP: {new_ip}")

    ### Update the record with the new IP:
    response = route53_client.change_resource_record_sets(
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
    return response
