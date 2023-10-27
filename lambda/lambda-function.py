import boto3
import os

# Hard coded for now, will pas in as an env var eventually:
ECS_CLUSTER_NAME = "GameManagerStack-v3-ecs-cluster"
ECS_CLUSTER_SERVICE = "GameManagerStack-v3-ec2serviceServiceCAD2C483-tiSJTL32Tqfh"

required_vars = ["AWS_REGION"]
missing_vars = [x for x in required_vars if not os.environ.get(x)]
if any(missing_vars):
    raise RuntimeError(f"Missing environment vars: {' '.join(missing_vars)}")

def lambda_handler(event, context):
    # This lambda is apart of a stack, so ecs will always be in
    # the same region as this function:
    ecs_client = boto3.client('ecs', region_name=os.environ['AWS_REGION'])
    ## Is it worth checking desired count before setting?
    #       How much time does grabbing it take? Are there any downsides
    #       to setting to the same/current value? (doesn't look like it.)
    service = ecs_client.update_service(
        cluster=ECS_CLUSTER_NAME,
        service=ECS_CLUSTER_SERVICE,
        desiredCount=0, # <--- Or 1.
    )
    # Now wait for it to be done updating:
    # (I think this?): https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ecs/waiter/ServicesStable.html
    # Turn down the WaiterConfig.Delay if you can. 15sec is WAY to slow.

def get_ecs_service():
    cfn_client = boto3.client('cloudformation', region_name=os.environ['AWS_REGION'])

# I accedently went in a loop, but some of this is a good example
# and might be useful :shrug:
def get_cluster_name_from_cluster_name():
    ecs_clent = boto3.client('ecs', region_name=os.environ['AWS_REGION'])
    clusters = ecs_clent.describe_clusters(clusters=[ ECS_CLUSTER_NAME ])
    assert len(clusters['clusters']) == 1, f"DEBUG ERROR: Could not find cluster. (Got {len(clusters['clusters'])} back)."
    game_cluster = clusters['clusters'][0]
    print(game_cluster["clusterArn"])
    print(game_cluster["clusterName"])
    # can also get number of tasks, etc...

def get_service_name_from_name():
    ecs_clent = boto3.client('ecs', region_name=os.environ['AWS_REGION'])
    services = ecs_clent.describe_services(cluster=ECS_CLUSTER_NAME, services=[ECS_CLUSTER_SERVICE])
    assert len(services['services']) == 1, f"DEBUG ERROR: Could not find service. (Got {len(services['services'])} back)."
    game_service = services["services"][0]