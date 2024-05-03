
import os
import json

import boto3
import botocore

required_vars = [
    "ASG_NAME",
    "TASK_DEFINITION",
    "METRIC_NAMESPACE",
    "METRIC_NAME",
    "METRIC_UNIT",
    "METRIC_DIMENSIONS",
]
missing_vars = [x for x in required_vars if not os.environ.get(x)]
if any(missing_vars):
    raise RuntimeError(f"Missing environment vars: [{', '.join(missing_vars)}]")

# Boto3 Clients/Waiters:
#    Can get cached if function is reused, keep clients that are *always* hit here:
asg_client = boto3.client('autoscaling')
ssm_client = boto3.client('ssm')
ssm_command_waiter = ssm_client.get_waiter('command_executed')
cloudwatch_client = boto3.client('cloudwatch')

# Dimension map for cloudwatch:
# Load the metric dimension map:
dimensions_input = json.loads(os.environ["METRIC_DIMENSIONS"])
# Change it to the format boto3 cloudwatch wants:
dimension_map = [{"Name": k, "Value": v} for k, v in dimensions_input.items()]

def lambda_handler(event, context) -> None:
    print(json.dumps({"Event": event, "Context": context}, default=str))
    instance_id = get_acg_instance_id()
    num_connections = get_instance_connections(instance_id)
    push_to_cloudwatch_metric(num_connections)

def push_to_cloudwatch_metric(num_connections: int) -> None:
    cloudwatch_client.put_metric_data(
        Namespace=os.environ["METRIC_NAMESPACE"],
        MetricData=[{
            'MetricName': os.environ["METRIC_NAME"],
            'Dimensions': dimension_map,
            'Unit': os.environ["METRIC_UNIT"],
            'Value': num_connections,
        }],
    )

def get_instance_connections(instance_id: str) -> int:
    ## Run the Command:
    response = ssm_client.send_command(
        InstanceIds=[instance_id],
        Comment=f"Check Connections on {instance_id}",
        DocumentName="AWS-RunShellScript",
        Parameters={
            'commands': [
                ## The best way I could find to get the container ID:
                # https://stackoverflow.com/questions/44550138/naming-docker-containers-on-start-ecs#44551679
                f'container_id=$(docker container ls --quiet --filter label=com.amazonaws.ecs.task-definition-family={os.environ["TASK_DEFINITION"]})',
                ## If the task hasn't started yet, the container won't exist, and container_id will be blank:
                'if test -z "$container_id"; then echo "Task has not started yet. Exiting."; exit -1; fi',
                ## Run netstat from outside the container, so it doesn't have to be installed inside:
                # https://stackoverflow.com/questions/40350456/docker-any-way-to-list-open-sockets-inside-a-running-docker-container
                'docker_pid=$(docker inspect -f "{{.State.Pid}}" $container_id)',
                'num_docker_conn=$(nsenter --target $docker_pid --net netstat | grep ESTABLISHED | wc -l)',
                ## Also stay up if someone is SSH-ed in:
                'num_ssh_conn=$(netstat -tan | grep ":22" | grep ESTABLISHED | wc -l)',
                ## Now "return" the info as json:
                'jq --null-input \'$ARGS.named\' --argjson num_docker_conn "$num_docker_conn" --argjson num_ssh_conn "$num_ssh_conn"',
            ],
        }
    )
    command_id = response['Command']['CommandId']
    # You get no feedback if the command fails. You can use this to look up the error
    #    in the console, but I couldn't find a way to get output there either:
    print(f"SSM Command ID: {command_id}")
    try:
        ## Wait for it:
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ssm/waiter/CommandExecuted.html
        ssm_command_waiter.wait(
            CommandId=command_id,
            InstanceId=instance_id,
            WaiterConfig={
                "Delay": 1,
                "MaxAttempts": 120,
            },
        )
    except botocore.exceptions.WaiterError as e:
        raise RuntimeError("Could not get connection count. Is the task running?") from e

    ## Get the output:
    output = ssm_client.get_command_invocation(
        CommandId=command_id,
        InstanceId=instance_id,
    )

    try:
        num_connections = json.loads(output['StandardOutputContent'])
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Could not parse output from command: {output['StandardOutputContent']}") from e

    # Log the Json for cloudwatch:
    print(json.dumps(num_connections, default=str))
    # Return the number of connections:
    return sum(num_connections.values())

def get_acg_instance_id() -> str:
    asg_info = asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[os.environ["ASG_NAME"]])['AutoScalingGroups'][0]
    running_instances = [x for x in asg_info['Instances'] if x['LifecycleState'] == "InService"]
    # There should only be one running instance, if there's more/less, something is wrong:
    # if lambda errors too many times, the cloudwatch alarm should spin things down anyways.
    assert len(running_instances) == 1, f"Expected 1 running instance, got '{len(running_instances)}'."
    return running_instances[0]['InstanceId']
