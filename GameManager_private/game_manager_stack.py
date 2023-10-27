
import os

from aws_cdk import (
    Stack,
    CfnParameter,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
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
            # nat_gateways=0,   # <-- I think this is what was breaking the stack, it should work now
                                #       BUT you're looking at ~$64/month for two NAT gateways....
            max_azs=2,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name=f"public-{construct_id}",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name=f"private-{construct_id}",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ]
        )
        # TODO: Make sure ec2 instances can only deploy to private subnet

        ## VPC Endpoints:
        # NOTE: If we go completely private, we'll need endpoints for these if we use them:
        #           Secrets Manager, CloudWatch Logs
        #           https://docs.aws.amazon.com/AmazonECS/latest/developerguide/vpc-endpoints.html#ecs-vpc-endpoint-considerations
        ## Just for Logs:
        self.vpc_endpoint_cloudwatch = ec2.InterfaceVpcEndpoint(
            self, "vpc-endpoint-cloudwatch", vpc=self.vpc, service=ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH
        )
        ## Talk with / Register EC2 instances to the ECS Cluster:
        # TODO: These allow ALL traffic in AND out. Is that okay at this level?
        ecs_services = {
            # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_ec2/InterfaceVpcEndpointAwsService.html
            "vpc-endpoint-ecs-agent": ec2.InterfaceVpcEndpointAwsService.ECS_AGENT,
            "vpc-endpoint-ecs-telemetry": ec2.InterfaceVpcEndpointAwsService.ECS_TELEMETRY,
            "vpc-endpoint-ecs": ec2.InterfaceVpcEndpointAwsService.ECS,
        }
        for ecs_service_name, ecs_service_id in ecs_services.items():
            # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_ec2/IInterfaceVpcEndpoint.html
            ec2.InterfaceVpcEndpoint(self, ecs_service_name, vpc=self.vpc, service=ecs_service_id)
            # Can add extra permissions if needed:
            # https://docs.aws.amazon.com/AmazonECS/latest/developerguide/vpc-endpoints.html#vpc-endpoint-policy

        ## HTTPS Out Security Group:
        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_ec2/SecurityGroup.html
        self.sg_allow_https_out = ec2.SecurityGroup(self, "sg-https-traffic-out", vpc=self.vpc, allow_all_outbound=False)
        self.sg_allow_https_out.connections.allow_to(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(443),
            description="Allow HTTPS traffic OUT. For updates, and letting ECS talk with EC2 to register instances",
        )

        ## Permissions for inside the container:
        self.ec2_role = iam.Role(
            self,
            "ec2-execution-role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            description="This instance's permissions, inside the container",
        )
        ## Let it register to a ecs cluster:
        # https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-awsmanpol.html#instance-iam-role-permissions
        self.ec2_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonEC2ContainerServiceforEC2Role"))
        # self.ec2_role.add_to_policy(
        #     iam.PolicyStatement(
        #         effect=iam.Effect.ALLOW,
        #         resources=[],
        #         actions=[],
        #         conditions={
        #             "StringEquals": {"example-1": "example-2"}
        #         }
        #     )
        # )

        ## For Running Commands (on container creation I think?)
        self.ec2_user_data = ec2.UserData.for_linux()
        # self.ec2_user_data.add_commands()

        ## Contains the configuration information to launch an instance, and stores launch parameters
        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_ec2/LaunchTemplate.html
        self.launch_template = ec2.LaunchTemplate(
            self,
            "ASG-LaunchTemplate",
            instance_type=ec2.InstanceType("m5.large"),
            ## Needs to be an "EcsOptimized" image to register to the cluster
            # machine_image=ecs.EcsOptimizedImage.amazon_linux2(),
            # machine_image=ec2.MachineImage.latest_amazon_linux(), # <--- Check if this pulls 2023 or what (if EcsOptimizedImage version exists)
            machine_image=ecs.EcsOptimizedImage.amazon_linux(),
            user_data=self.ec2_user_data,
            # Needs to talk with ECS to register to the cluster:
            # (ec2 instances are launched inside this group)
            security_group=self.sg_allow_https_out,
            role=self.ec2_role,
        )

        ## A Fleet represents a managed set of EC2 instances:
        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_autoscaling/AutoScalingGroup.html
        self.auto_scaling_group = autoscaling.AutoScalingGroup(
            self,
            "ASG",
            vpc=self.vpc,
            launch_template=self.launch_template,
            desired_capacity=0,
            min_capacity=0,
            max_capacity=1,
            # IDK why I have to set this, the default is False. Maybe if you switch AMI's, the old AMI's
            # gain the protection? Test later and see if this needs to be set once the stack is more stable:
            new_instances_protected_from_scale_in=False,
        )

        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_ecs/Cluster.html
        self.ecs_cluster = ecs.Cluster(
            self,
            "ecs-cluster",
            cluster_name=f"{construct_id}-ecs-cluster",
            vpc=self.vpc,
        )

        ## This allows an ECS cluster to target a specific EC2 Auto Scaling Group for the placement of tasks.
        # Can ensure that instances are not prematurely terminated while there are still tasks running on them.
        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_ecs/AsgCapacityProvider.html
        self.capacity_provider = ecs.AsgCapacityProvider(
            self,
            "AsgCapacityProvider",
            # capacity_provider_name=f"{construct_id}-AsgCapacityProvider",
            auto_scaling_group=self.auto_scaling_group,
            # machine_image_type=ecs.MachineImageType.AMAZON_LINUX_2,
            # Let me delete the stack!!:
            enable_managed_termination_protection=False,
        )
        self.ecs_cluster.add_asg_capacity_provider(self.capacity_provider)

        ## The details of a task definition run on an EC2 cluster.
        # (Root task definition, attach containers to this)
        self.task_definition = ecs.Ec2TaskDefinition(
            self,
            "task-definition",
            # network_mode= bridge default, might change to aws_vpc if it doesn't work
            # execution_role= ecs agent permissions (Permissions to pull images from ECR, BUT will automatically create one if not specified)
            # task_role= permissions for inside the container
        )
        ## Details for the Minecraft Container:
        self.task_definition.add_container(
            "game-container",
            # image=ecs.ContainerImage.from_registry("itzg/minecraft-server"),
            image=ecs.ContainerImage.from_registry("amazon/amazon-ecs-sample"),
            ## Hard limit. Won't ever go above this
            # memory_limit_mib=999999999,
            ## Soft limit. Container will go down to this if under heavy load, but can go higher
            memory_reservation_mib=4*1024,
            # volumes= maybe persistent storage later on? Also has '.add_volume' method
        )

        ## This creates a service using the EC2 launch type on an ECS cluster
        self.ec2_service = ecs.Ec2Service(
            self,
            "ec2-service",
            cluster=self.ecs_cluster,
            task_definition=self.task_definition,
            desired_count=0,
            circuit_breaker={
                # "enable": True, # Just having circuit breaker defined will enable it
                "rollback": False # Don't keep trying to restart the container if it fails
            },
        )


        # self.execution_role = iam.Role(
        #     self,
        #     "ecs-execution-role",
        #     assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        #     role_name=f"{construct_id}-ecs-execution-role",
        # )
        # self.execution_role.add_to_policy(
        #     iam.PolicyStatement(
        #         effect=iam.Effect.ALLOW,
        #         resources=["*"],
        #         actions=[
        #             "ecr:GetAuthorizationToken",
        #             "ecr:BatchCheckLayerAvailability",
        #             "ecr:GetDownloadUrlForLayer",
        #             "ecr:BatchGetImage",

        #             "logs:CreateLogStream",
        #             "logs:PutLogEvents",
        #         ]
        #     )
        # )
