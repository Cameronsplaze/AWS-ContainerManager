
import os
import json

import boto3
import botocore

## Check for required environment variables:
required_vars = [
    # For getting instance ID:
    "ASG_NAME",
    # For getting right docker container on instance:
    "TASK_DEFINITION",
    # How we should check for connections:
    "CONNECTION_TYPE",
    # Which metric to update in cloudwatch:
    "METRIC_NAME_ACTIVITY_COUNT",
    "METRIC_NAME_SSH_CONNECTIONS",
    "METRIC_NAMESPACE",
    "METRIC_UNIT",
    "METRIC_DIMENSIONS",
]
missing_vars = [x for x in required_vars if not os.environ.get(x)]
if any(missing_vars):
    raise RuntimeError(f"Missing environment vars: [{', '.join(missing_vars)}]")

# Connection type for this lambda:
connection_type = os.environ["CONNECTION_TYPE"].upper()
if connection_type == "TCP":
    assert os.environ.get("TCP_PORT"), "You must declare which port to check on for TCP connections! (TCP_PORT)"
elif connection_type == "UDP":
    pass
else:
    raise RuntimeError(f"Invalid connection type! Not yet supported: '{connection_type}'.")



### Boto3 Clients/Waiters:
#    Can get cached if function is reused, keep clients that are *always* hit here:
asg_client = boto3.client('autoscaling')
ssm_client = boto3.client('ssm')
ssm_command_waiter = ssm_client.get_waiter('command_executed')
cloudwatch_client = boto3.client('cloudwatch')

### Dimension map for cloudwatch:
# Load the metric dimension map:
dimensions_input = json.loads(os.environ["METRIC_DIMENSIONS"])
# Change it to the format boto3 cloudwatch wants:
dimension_map = [{"Name": k, "Value": v} for k, v in dimensions_input.items()]


def lambda_handler(event, context) -> None:
    print(json.dumps({"Event": event, "Context": context}, default=str))
    instance_id = get_acg_instance_id()
    ssm_commands = build_ssm_command_script()
    connections = get_instance_connections(instance_id, ssm_commands)

    push_to_cloudwatch_metric(os.environ["METRIC_NAME_ACTIVITY_COUNT"], connections["activity_count"])
    push_to_cloudwatch_metric(os.environ["METRIC_NAME_SSH_CONNECTIONS"], connections["num_ssh_conn"])

def push_to_cloudwatch_metric(metric_name: str, value: int) -> None:
    cloudwatch_client.put_metric_data(
        Namespace=os.environ["METRIC_NAMESPACE"],
        MetricData=[{
            'MetricName': metric_name,
            'Dimensions': dimension_map,
            'Unit': os.environ["METRIC_UNIT"],
            'Value': value,
        }],
    )

def build_ssm_command_script() -> list:
    ### Build the script that we'll run on the instance:
    ssm_command = []
    ## Set 'container_id' and 'docker_pid', so future commands can use them:
    ssm_command.extend([
        ## The best way I could find to get the container ID:
        # https://stackoverflow.com/questions/44550138/naming-docker-containers-on-start-ecs#44551679
        f'container_id=$(docker container ls --quiet --filter label=com.amazonaws.ecs.task-definition-family={os.environ["TASK_DEFINITION"]})',
        ## If the task hasn't started yet, the container won't exist, and container_id will be blank:
        'if test -z "$container_id"; then echo "Task has not started yet. Exiting."; exit -1; fi',
        'docker_pid=$(docker inspect -f "{{.State.Pid}}" $container_id)',
    ])
    ## Get the number of Host SSH Connections, don't spin down if someone is SSH-ed in:
    #       (Count's SFTP connections too, someone might be copying stuff in/out)
    ssm_command.extend([
        'num_ssh_conn=$(netstat --tcp --numeric | grep ":22" | grep ESTABLISHED | wc -l)',
    ])
    ## Run netstat or nstat from outside the container, so it doesn't have to be installed inside:
    # https://stackoverflow.com/questions/40350456/docker-any-way-to-list-open-sockets-inside-a-running-docker-container
    if connection_type == "TCP":
        # Counts the number of PLAYERS connected
        ssm_command.extend([
            f'activity_count=$(nsenter --target $docker_pid --net netstat --tcp --numeric | grep ":{os.environ["TCP_PORT"]}" | grep ESTABLISHED | wc -l)',
        ])
    elif connection_type == "UDP":
        # Counts the number of udp PACKETS sent over time
        ssm_command.extend([
            # Grab how many UDP packets were transferred since last nstat call:
            #      (Both UdpInDatagrams and UdpOutDatagrams)
            "list_udp_packets=$( nsenter --target $docker_pid --net nstat --zeros | awk '/Udp(In|Out)Datagrams/{print $2}' | paste -sd+ )",
            # Add them together - (Currently in literal format: "num1+num2")
            'activity_count=$(( $list_udp_packets ))',
        ])
    ## Finally Save the info as json:
    ssm_command.extend([
        'jq --null-input \'$ARGS.named\' --argjson activity_count "$activity_count" --argjson num_ssh_conn "$num_ssh_conn"',
    ])
    return ssm_command

def get_instance_connections(instance_id: str, ssm_commands: list) -> dict:
    ### Run the Command:
    response = ssm_client.send_command(
        InstanceIds=[instance_id],
        Comment=f"Check Connections on {instance_id}",
        DocumentName="AWS-RunShellScript",
        Parameters={ 'commands': ssm_commands }
    )
    # You get no feedback if the command fails. You can use this to look up the error
    #    in the console, but I couldn't find a way to get output there either:
    print(json.dumps(response, default=str))
    command_id = response['Command']['CommandId']
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
        raise RuntimeError(json.dumps({
            "msg": "Could not get connection count. Is the task running?",
            "task_def": os.environ["TASK_DEFINITION"],
            "instance_id": instance_id,
            "error": str(e),
        })) from e

    ## Get the output:
    output = ssm_client.get_command_invocation(
        CommandId=command_id,
        InstanceId=instance_id,
    )
    print(json.dumps(output, default=str))

    try:
        connections = json.loads(output['StandardOutputContent'])
    except KeyError as e:
        raise RuntimeError(f"Key 'StandardOutputContent' not in output: '{output}'") from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Could not load output to json: '{output['StandardOutputContent']}'") from e

    ## Return the number of connections, in the form of:
    # {
    #     "activity_count": int,
    #     "num_ssh_conn": int,
    # }
    print(json.dumps(connections, default=str))
    return connections

def get_acg_instance_id() -> str:
    asg_info = asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[os.environ["ASG_NAME"]])['AutoScalingGroups'][0]
    running_instances = [x for x in asg_info['Instances'] if x['LifecycleState'] == "InService"]
    # There should only be one running instance, if there's more/less, something is wrong:
    # if lambda errors too many times, the cloudwatch alarm should spin things down anyways.
    assert len(running_instances) == 1, f"Expected 1 running instance, got '{len(running_instances)}'."
    print(f"Found one instance: {running_instances[0]['InstanceId']}")
    return running_instances[0]['InstanceId']
