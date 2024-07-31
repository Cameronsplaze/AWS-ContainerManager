
"""
Lambda code for starting the system when someone tries to connect.
"""

import os
import json

import boto3
from botocore.config import Config

required_vars = [
    "ASG_NAME",
    "MANAGER_STACK_REGION",
    # For not letting the system spin down if someone is trying to connect:
    "METRIC_NAMESPACE",
    "METRIC_NAME",
    "METRIC_THRESHOLD",
    "METRIC_UNIT",
    "METRIC_DIMENSIONS",
]
missing_vars = [x for x in required_vars if not os.environ.get(x)]
if any(missing_vars):
    raise RuntimeError(f"Missing environment vars: [{', '.join(missing_vars)}]")

# Boto3 Clients:
config = Config(region_name=os.environ["MANAGER_STACK_REGION"])
cloudwatch_client = boto3.client('cloudwatch', config=config)
asg_client = boto3.client('autoscaling', config=config)

def lambda_handler(event, context):
    """ Main function of the lambda. """
    print(json.dumps({"Event": event, "Context": context}, default=str))

    ### Let the metric know someone is trying to connect, to stop it
    ### from alarming and spinning down the system:
    ###   (Also if the system is in alarm, this resets it so it can spin down again)
    ## TODO: Add this to the Design docs. This is important if the container
    ##    is auto-updating to the latest version, and you can't join until
    ##    the update finishes. Since the container spins up based on connections,
    ##    this is the best way I can think of to handle auto-updates.
    dimensions_input = json.loads(os.environ["METRIC_DIMENSIONS"])
    # Change it to the format boto3 cloudwatch wants:
    dimension_map = [{"Name": k, "Value": v} for k, v in dimensions_input.items()]
    cloudwatch_client.put_metric_data(
        Namespace=os.environ["METRIC_NAMESPACE"],
        MetricData=[{
            'MetricName': os.environ["METRIC_NAME"],
            'Dimensions': dimension_map,
            'Unit': os.environ["METRIC_UNIT"],
            # One greater than the threshold, to make sure the alarm doesn't error:
            'Value': 1+int(os.environ["METRIC_THRESHOLD"]),
        }],
    )

    ## Spin up the instance. The instance-StateChange-hook will do the rest:
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/autoscaling.html#AutoScaling.Client.update_auto_scaling_group
    asg_client.update_auto_scaling_group(
        AutoScalingGroupName=os.environ["ASG_NAME"],
        DesiredCapacity=1,
    )
