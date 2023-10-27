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

DOCKER_IMAGE = "amazon/amazon-ecs-sample"
# DOCKER_IMAGE = "nginx:latest"
PORT = 80

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

        # Create a Public VPC to run instances in:
        self.vpc = ec2.Vpc(
            self,
            "Vpc",
            nat_gateways=0,
            max_azs=2,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name=f"public-{construct_id}",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                )
            ]
        )
        # NOTE: No cost for Internet Gateways. Try to avoid having instances
        # getting public IP's by putting them behind a network load balancer

        ## ECS / EC2 Security Group (Same since using bridge I think?):
        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_ec2/SecurityGroup.html
        self.sg_ecs_traffic = ec2.SecurityGroup(self, "sg-https-traffic-out", vpc=self.vpc, allow_all_outbound=False)
        self.sg_allow_https_out.connections.allow_to(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(443),
            description="Allow HTTPS traffic OUT. Let ECS talk with EC2 to register instances",
        )
        self.sg_ecs_traffic.connections.allow_from(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(PORT),  # <---- NOTE: TCP is hard-coded here too. Look into if we need to support UDP too.
            description="Game port to open traffic IN from",
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
            # Lets Specific traffic to/from the instance:
            security_group=self.sg_ecs_traffic,
            user_data=self.ec2_user_data,
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
        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_ecs/TaskDefinition.html
        self.task_definition = ecs.Ec2TaskDefinition(
            self,
            "task-definition",
            ## TODO: Says this can be locked down the most, and works with both windows/linux containers:
            ## BUT no way to assign it a public IP I can find. Compare with other MC Stack, see if they create
            ## A NAT or not. If they do, they're hella expensive though. (https://github.com/aws/aws-cdk/issues/13348)
            # network_mode=ecs.NetworkMode.AWS_VPC,
            # execution_role= ecs agent permissions (Permissions to pull images from ECR, BUT will automatically create one if not specified)
            # task_role= permissions for inside the container
        )
        ## Details for the Minecraft Container:
        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_ecs/TaskDefinition.html#aws_cdk.aws_ecs.TaskDefinition.add_container
        self.task_definition.add_container(
            "game-container",
            # image=ecs.ContainerImage.from_registry("itzg/minecraft-server"),
            image=ecs.ContainerImage.from_registry(DOCKER_IMAGE),
            port_mappings=[
                ecs.PortMapping(host_port=PORT, container_port=PORT, protocol=ecs.Protocol.TCP),
            ],
            ## Hard limit. Won't ever go above this
            # memory_limit_mib=999999999,
            ## Soft limit. Container will go down to this if under heavy load, but can go higher
            memory_reservation_mib=4*1024,
            # volumes= maybe persistent storage later on? Also has '.add_volume' method
        )

        ## This creates a service using the EC2 launch type on an ECS cluster
        # TODO: If you edit this in the console, there's a way to add "placement template - one per host" to it. Can't find the CDK equivalent rn.
        # https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_ecs/Ec2Service.html
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
            ## security_groups is only valid with AWS_VPC network mode:
            # security_groups=[self.sg_allow_game_traffic_in],
        )

        ## TODO: When getting to auto-scaling ec2 instance, this might help? Supposed to grab
        # the new IP address early:
        #   - https://github.com/aws/aws-cdk/blob/v1-main/packages/@aws-cdk-containers/ecs-service-extensions/lib/extensions/assign-public-ip/assign-public-ip.ts
        #   - https://stackoverflow.com/questions/68941663/is-there-anyway-to-determine-the-public-ip-of-a-fargate-container-before-it-beco
    

