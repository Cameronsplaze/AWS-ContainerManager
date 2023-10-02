
import os

from aws_cdk import (
    Stack,
    CfnParameter,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_iam as iam,
    aws_autoscaling as autoscaling,
)
from constructs import Construct

def get_param(stack: Stack, key: str, default: str=None, param_type: str="String", description: str="") -> str:
    val = os.environ.get(key) or default
    if val is None:
        raise ValueError(f"Missing required parameter: '{key}', and no default is set.")

    # This is to see what the stack was deployed with in the cfn parameters tab:
    CfnParameter(
        stack,
        key,
        type=param_type,
        default=val,
        # Since changing it in the console won't do anything, don't let them:
        allowed_values=[val],
        description=f"{description}{' ' if description else ''}(Re-deploy to change me!)"
    )

    # If you're expecting a number, change it away from a string:
    #   (CfnParameter *wants* the input as a string, but nothing else does)
    if param_type == "Number":
        val = float(val) if "." in val else int(val)
    return val

class GameManagerStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.vpc = ec2.Vpc(
            self,
            "Vpc",
            nat_gateways=0,
            max_azs=2,
        )


        self.ecs_cluster = ecs.Cluster(
            self,
            "ecs-cluster",
            cluster_name=f"{construct_id}-ecs-cluster",
            vpc=self.vpc,
        )

        self.execution_role = iam.Role(
            self,
            "ecs-execution-role",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            role_name=f"{construct_id}-ecs-execution-role",
        )
        self.execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                resources=["*"],
                actions=[
                    "ecr:GetAuthorizationToken",
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchGetImage",

                    "logs:CreateLogStream", 
                    "logs:PutLogEvents",
                ]
            )
        )

        self.auto_scaling_group = autoscaling.AutoScalingGroup(self, f"{construct_id}-ASG",
            vpc=self.vpc,
            instance_type=ec2.InstanceType("m5.large"),
            machine_image=ecs.EcsOptimizedImage.amazon_linux(),
            # Lambda will update this:
            desired_capacity=0,
            # Make it clear this can change by one:
            min_capacity=0,
            max_capacity=1,
        )
        self.capacity_provider = ecs.AsgCapacityProvider(self, f"{construct_id}-AsgCapacityProvider", auto_scaling_group=self.auto_scaling_group)
        self.ecs_cluster.add_asg_capacity_provider(self.capacity_provider)

        self.task_definition = ecs.Ec2TaskDefinition(
            self,
            "task-definition",
            # network_mode= bridge default, might change to aws_vpc if it doesn't work
            # execution_role= ecs agent permissions
            # task_role= permissions for inside the container
            # volumes= maybe persistent storage later on? Also has '.add_volume' method
        )
        self.task_definition.add_container(
            "game-container",
            # image=ecs.ContainerImage.from_registry("itzg/minecraft-server"),
            image=ecs.ContainerImage.from_registry("amazon/amazon-ecs-sample"),
            # Hard limit. Won't go above this
            # memory_limit_mib=999999999,
            # Soft limit. Container will use this if under heavy load, but can go higher
            memory_reservation_mib=4*1024,
        )
        self.ec2_service = ecs.Ec2Service(
            self,
            "ec2-service",
            cluster=self.ecs_cluster,
            task_definition=self.task_definition,
            desired_count=0,
            circuit_breaker={
                # "enable": True, # Just having circuit breaker defined will enable it
                "rollback": False
            },
        )
