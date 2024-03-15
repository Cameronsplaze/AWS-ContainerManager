
import os

import boto3


required_vars = ["ECS_CLUSTER_NAME", "ECS_SERVICE_NAME", "ASG_NAME", "WATCH_INSTANCE_RULE"]
missing_vars = [x for x in required_vars if not os.environ.get(x)]
if any(missing_vars):
    raise RuntimeError(f"Missing environment vars: [{', '.join(missing_vars)}]")

# Boto3 Clients:
asg_client = boto3.client('autoscaling')
ecs_client = boto3.client('ecs')
ecs_service_waiter = ecs_client.get_waiter('services_stable')
events_client = boto3.client('events')


def lambda_handler(event, context):
    print("DEBUG INFO")
    print({"Event": event, "Context": context})
    if False:
        print("TODO: Trigger system on when someone connects to DNS:")
        update_ecs_container(switch=True)
    elif event["source"] == "aws.cloudwatch" and event.get("alarmData")["state"]["value"] == "ALARM":
        alarm_name = event["alarmData"]["alarmName"]
        print(f"Alarm '{alarm_name}' triggered, spinning down container!")
        update_ecs_container(switch=False)
    else:
        print({"Event": event, "Context": context})
        raise RuntimeError("Unknown event hit! Unsupported state, how'd you get here?")

def update_ecs_container(switch: bool) -> None:
    """
    switch: bool - True to spin up, False to spin down
    """
    # If spinning up, first spin up the container, then the service
    # If spinning down, first spin down the service, then the container
    if switch:
        update_asg(desired_count=1, wait_to_finish=True)
        update_ecs_service(desired_count=1, wait_to_finish=False)
    else:
        update_ecs_service(desired_count=0, wait_to_finish=True)
        update_asg(desired_count=0, wait_to_finish=False)
        events_client.disable_rule(Name=os.environ["WATCH_INSTANCE_RULE"])


def update_asg(desired_count: int, wait_to_finish: bool) -> dict:
    print(f"Update ASG Start - desired count: {desired_count}")
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/autoscaling.html#AutoScaling.Client.update_auto_scaling_group
    response = asg_client.update_auto_scaling_group(
        AutoScalingGroupName=os.environ["ASG_NAME"],
        DesiredCapacity=desired_count,
    )
    # If asg is updated first, you need to wait for it to finish before updating the ecs
    # If it's last, just skip it.
    if wait_to_finish:
        print("Update ASG - Start Waiting")
        # No idea how to wait for this to finish. The ecs service has
        # a wait, one here just would speed things up.
        # I asked about it here: https://stackoverflow.com/questions/78044335/aws-boto3-how-to-wait-for-autoscaling-group-to-finish-scaling
        print("Update ASG - End Waiting")
    return response


def update_ecs_service(desired_count: int, wait_to_finish: bool) -> dict:
    print(f"Update ECS Service Start - desired count: {desired_count}")
    response = ecs_client.update_service(
        cluster=os.environ["ECS_CLUSTER_NAME"],
        service=os.environ["ECS_SERVICE_NAME"],
        desiredCount=desired_count,
    )
    # If ecs is updated first, you need to wait for it to finish before updating the asg
    # If it's last, just skip it.
    if wait_to_finish:
        # Now wait for it to be done updating:
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ecs/waiter/ServicesStable.html
        print("Update ECS Service - Start Waiting")
        ecs_service_waiter.wait(
            cluster=os.environ["ECS_CLUSTER_NAME"],
            services=[os.environ["ECS_SERVICE_NAME"]],
            WaiterConfig={
                "Delay": 1,
                "MaxAttempts": 120,
            },
        )
        print("Update ECS Service - End Waiting")
    return response

if __name__ == "__main__":
    update_ecs_container(switch=True)
