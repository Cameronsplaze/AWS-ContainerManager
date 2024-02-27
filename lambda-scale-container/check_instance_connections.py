
import os
import boto3

required_vars = ["AWS_REGION", "ASG_NAME", "DOCKER_IMAGE", "DOCKER_PORT", "TASK_DEFINITION"]
missing_vars = [x for x in required_vars if not os.environ.get(x)]
if any(missing_vars):
    raise RuntimeError(f"Missing environment vars: {', '.join(missing_vars)}")

# Boto3 Clients:
asg_client = boto3.client('autoscaling')
ssm_client = boto3.client('ssm')

def lambda_handler(event, context):
    pass


def get_acg_instance(asg_name: str) -> dict:
    # TODO: Make this not fail with [0]. Not sure yet what's best todo, return or throw?
    asg_info = asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])['AutoScalingGroups'][0]
    # TODO: Same here as above. Just for development for now though.
    # (Also this *could* have more than one, if one is scaling down as another scales up...)
    instance = asg_info['Instances'][0]
    return instance

def run_command_on_instance(instance_id: str):
    ## Run the Command:
    response = ssm_client.send_command(
        InstanceIds=[instance_id],
        Comment="Seeing if anyone is connected to the server.",
        DocumentName="AWS-RunShellScript",
        Parameters={
            'commands': [
                ## The best way I could find to get the container ID:
                # https://stackoverflow.com/questions/44550138/naming-docker-containers-on-start-ecs#44551679
                f'container_id=$(docker container ls --quiet --filter label=com.amazonaws.ecs.task-definition-family={os.environ["TASK_DEFINITION"]})',
                ## Run netstat from outside the container, so it doesn't have to be installed inside:
                # https://stackoverflow.com/questions/40350456/docker-any-way-to-list-open-sockets-inside-a-running-docker-container
                'docker_pid=$(docker inspect -f "{{.State.Pid}}" $container_id)',
                'nsenter --target $docker_pid --net netstat | grep ESTABLISHED | wc -l',
            ]
        }
    )
    # print(response)
    command_id = response['Command']['CommandId']

    ## Wait for it:
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ssm/waiter/CommandExecuted.html
    waiter = ssm_client.get_waiter('command_executed')
    waiter.wait(
        CommandId=command_id,
        InstanceId=instance_id,
        WaiterConfig={
            "Delay": 1,
            "MaxAttempts": 120,
        },
    )

    ## Get the output:
    output = ssm_client.get_command_invocation(
        CommandId=command_id,
        InstanceId=instance_id,
    )
    print(output["StandardOutputContent"])
    return output

if __name__ == "__main__":
    instance_info = get_acg_instance(os.environ["ASG_NAME"])
    results = run_command_on_instance(instance_info['InstanceId'])
