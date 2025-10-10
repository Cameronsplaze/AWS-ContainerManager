
"""
Lambda for spinning down the ASG if the container ever throws.
"""

import os
import json

import boto3


required_vars = [
    "ASG_NAME",
]

missing_vars = [x for x in required_vars if not os.environ.get(x)]
if any(missing_vars):
    raise RuntimeError(f"Missing environment vars: [{', '.join(missing_vars)}]")

asg_client = boto3.client('autoscaling')

def lambda_handler(event, context):
    """ Main function of the lambda. """
    print(json.dumps({"Event": event, "Context": context}, default=str))

    ## Spin down the instance. The instance-StateChange-hook will do the rest:
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/autoscaling.html#AutoScaling.Client.update_auto_scaling_group
    asg_client.update_auto_scaling_group(
        AutoScalingGroupName=os.environ["ASG_NAME"],
        DesiredCapacity=0,
    )
