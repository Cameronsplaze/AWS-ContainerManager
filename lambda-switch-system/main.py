
import os
import json

import boto3


required_vars = [
    "ECS_CLUSTER_NAME",
    "ECS_SERVICE_NAME",
    "ASG_NAME",
    "WATCH_INSTANCE_RULE",
    "SNS_TOPIC_ARN_SPIN_DOWN",
    # For not letting the system spin down if someone is trying to connect:
    "METRIC_NAMESPACE",
    "METRIC_NAME",
    "METRIC_UNIT",
    "METRIC_DIMENSIONS",
]
missing_vars = [x for x in required_vars if not os.environ.get(x)]
if any(missing_vars):
    raise RuntimeError(f"Missing environment vars: [{', '.join(missing_vars)}]")

# Boto3 Clients:
asg_client = boto3.client('autoscaling')
events_client = boto3.client('events')


def lambda_handler(event, context):
    print(json.dumps({"Event": event, "Context": context}, default=str))

    ### First figure out if you're spinning up or down the system:
    # Spin up if a DNS record is hit:
    if False:
        print("TODO: Trigger system on when someone connects to DNS:")
        spin_system_up = True
    # Spin down if a SNS event comes in, AND it's from the right SNS topic:
    elif event.get("Records") and len(event["Records"]) == 1 \
        and event["Records"][0]["EventSource"] == "aws:sns" \
        and event["Records"][0]["Sns"]["TopicArn"] == os.environ["SNS_TOPIC_ARN_SPIN_DOWN"]:
            spin_system_up = False
    else:
        raise RuntimeError("Unknown event hit! Unsupported state, how'd you get here?")

    print(f"Event hit: Spinning system {'up' if spin_system_up else 'down'}.")

    # If system is spinning UP:
    if spin_system_up:
        ### Let the metric know someone is trying to connect, to stop it
        ### from alarming and spinning down the system:
        ## TODO: Add this to the Design docs. This is important if the container
        ##    is auto-updating to the latest version, and you can't join until
        ##    the update finishes. Since the container spins up based on connections,
        ##    this is the best way I can think of to handle auto-updates.
        dimensions_input = json.loads(os.environ["METRIC_DIMENSIONS"])
        # Change it to the format boto3 cloudwatch wants:
        dimension_map = [{"Name": k, "Value": v} for k, v in dimensions_input.items()]
        cloudwatch_client = boto3.client('cloudwatch')
        cloudwatch_client.put_metric_data(
            Namespace=os.environ["METRIC_NAMESPACE"],
            MetricData=[{
                'MetricName': os.environ["METRIC_NAME"],
                'Dimensions': dimension_map,
                'Unit': os.environ["METRIC_UNIT"],
                'Value': 1,
            }],
        )
        asg_desired_count = 1

    # If system is spinning DOWN:
    else:
        ## Turn off everything:
        ecs_client = boto3.client('ecs')
        ecs_client.update_service(
            cluster=os.environ["ECS_CLUSTER_NAME"],
            service=os.environ["ECS_SERVICE_NAME"],
            desiredCount=0,
        )
        ### I don't think there's any reason to wait for the service here?
        # ecs_service_waiter = ecs_client.get_waiter('services_stable')
        # ecs_service_waiter.wait(
        #     cluster=os.environ["ECS_CLUSTER_NAME"],
        #     services=[os.environ["ECS_SERVICE_NAME"]],
        #     WaiterConfig={
        #         "Delay": 1,
        #         "MaxAttempts": 120,
        #     },
        # )
        events_client.disable_rule(Name=os.environ["WATCH_INSTANCE_RULE"])
        asg_desired_count = 0

    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/autoscaling.html#AutoScaling.Client.update_auto_scaling_group
    asg_client.update_auto_scaling_group(
        AutoScalingGroupName=os.environ["ASG_NAME"],
        DesiredCapacity=asg_desired_count,
    )
