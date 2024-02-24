
import os
from time import sleep

import boto3


# Hard coded for now, will pass in as an env var eventually:
ECS_CLUSTER_NAME = "GameManagerStack-ecs-cluster"
ECS_CLUSTER_SERVICE = "GameManagerStack-ec2serviceServiceCAD2C483-TjTSbRQFMVHo"
ASG_NAME = "GameManagerStack-ASG46ED3070-FEtdKSzDl6ds"

required_vars = ["AWS_REGION"]
missing_vars = [x for x in required_vars if not os.environ.get(x)]
if any(missing_vars):
    raise RuntimeError(f"Missing environment vars: {' '.join(missing_vars)}")

# Boto3 Clients:
asg_client = boto3.client('autoscaling')
ecs_client = boto3.client('ecs', region_name=os.environ['AWS_REGION'])

def lambda_handler(event, context):
    pass

def update_ecs_container(spin_up_container: bool) -> None:
    # If spinning up, first spin up the container, then the service
    # If spinning down, first spin down the service, then the container
    if spin_up_container:
        update_asg(desired_count=1)
        update_ecs_service(desired_count=1)
    else:
        update_ecs_service(desired_count=0)
        update_asg(desired_count=0)




def update_asg(desired_count: int) -> dict:
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/autoscaling.html#AutoScaling.Client.update_auto_scaling_group
    response = asg_client.update_auto_scaling_group(
        AutoScalingGroupName=ASG_NAME,
        DesiredCapacity=desired_count,
    )
    # No idea how to wait for this to finish. The ecs service has
    # a wait, one here just would speed things up.
    # I asked about it here: https://stackoverflow.com/questions/78044335/aws-boto3-how-to-wait-for-autoscaling-group-to-finish-scaling
    return response


def update_ecs_service(desired_count: int) -> dict:
    response = ecs_client.update_service(
        cluster=ECS_CLUSTER_NAME,
        service=ECS_CLUSTER_SERVICE,
        desiredCount=desired_count,
    )
    # Now wait for it to be done updating:
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ecs/waiter/ServicesStable.html
    waiter = ecs_client.get_waiter('services_stable')
    print("Start Waiting")
    waiter.wait(
        cluster=ECS_CLUSTER_NAME,
        services=[ECS_CLUSTER_SERVICE],
        WaiterConfig={
            "Delay": 1,
            "MaxAttempts": 120,
        },
    )
    print("End Waiting")
    return response


update_ecs_container(spin_up_container=False)
