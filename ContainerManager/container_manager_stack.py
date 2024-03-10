import os

from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    Tags,
    aws_lambda,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_iam as iam,
    aws_efs as efs,
    aws_logs as logs,
    aws_autoscaling as autoscaling,
    aws_route53 as route53,
    aws_events as events,
    aws_events_targets as targets,
    aws_cloudwatch as cloudwatch,
)
from constructs import Construct

from .base_stack import ContainerManagerBaseStack
from .get_param import get_param


INSTANCE_TYPE = "m5.large"
DATA_DIR = "/data"

container_environment = {
    "EULA": "TRUE",
    # From https://docker-minecraft-server.readthedocs.io/en/latest/configuration/misc-options/#openj9-specific-options
    "TUNE_VIRTUALIZED": "TRUE",
    "DIFFICULTY": "hard",
    "RCRON_PASSWORD": os.environ["RCRON_PASSWORD"],
}


class ContainerManagerStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, base_stack: ContainerManagerBaseStack, container_name_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.container_name_id = container_name_id
        self.docker_image = get_param(self, "DOCKER_IMAGE")
        self.docker_port = get_param(self, "DOCKER_PORT")
        self.instance_type = get_param(self, "INSTANCE_TYPE", default=INSTANCE_TYPE)

        self.vpc = base_stack.vpc
        self.sg_vpc_traffic = base_stack.sg_vpc_traffic
        self.hosted_zone = base_stack.hosted_zone

        ###########
        ## Setup Security Groups
        ###########
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2.SecurityGroup.html

        self.sg_vpc_traffic.connections.allow_from(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(self.docker_port),
            description="Game port to allow traffic IN from",
        )

        ## Security Group for EFS instance's traffic:
        self.sg_efs_traffic = ec2.SecurityGroup(
            self,
            f"{construct_id}-sg-efs-traffic",
            vpc=self.vpc,
            description="Traffic that can go into the EFS instance",
        )
        Tags.of(self.sg_efs_traffic).add("Name", f"{construct_id}/sg-efs-traffic")

        ## Security Group for container traffic:
        # TODO: Since someone could theoretically break into the container,
        #        lock down traffic leaving it too.
        #        (Should be the same as VPC sg BEFORE any stacks are added. Maybe have a base SG that both use?)
        self.sg_container_traffic = ec2.SecurityGroup(
            self,
            f"{construct_id}-sg-container-traffic",
            vpc=self.vpc,
            description="Traffic that can go into the container",
        )
        Tags.of(self.sg_container_traffic).add("Name", f"{construct_id}/sg-container-traffic")
        self.sg_container_traffic.connections.allow_from(
            ec2.Peer.any_ipv4(),           # <---- TODO: Is there a way to say "from outside vpc only"? The sg_vpc_traffic doesn't do it.
            # self.sg_vpc_traffic,
            ec2.Port.tcp(self.docker_port),
            description="Game port to open traffic IN from",
        )

        ## Now allow the two groups to talk to each other:
        self.sg_efs_traffic.connections.allow_from(
            self.sg_container_traffic,
            port_range=ec2.Port.tcp(2049),
            description="Allow EFS traffic IN - from container",
        )
        self.sg_container_traffic.connections.allow_from(
            # Allow efs traffic from within the Group.
            self.sg_efs_traffic,
            port_range=ec2.Port.tcp(2049),
            description="Allow EFS traffic IN - from EFS Server",
        )

        ###########
        ## Setup ECS
        ###########

        ## Cluster for all the games
        # This has to stay in this stack. A cluster represents a single "instance type"
        # sort of. This is the only way to tie the ASG to the ECS Service, one-to-one.
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.Cluster.html
        self.ecs_cluster = ecs.Cluster(
            self,
            f"{construct_id}-ecs-cluster",
            cluster_name=f"{construct_id}-ecs-cluster",
            vpc=self.vpc,
        )

        ## Permissions for inside the instance:
        self.ec2_role = iam.Role(
            self,
            f"{construct_id}-ec2-execution-role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            description="This instance's permissions, the host of the container",
        )

        ## Let the instance register itself to a ecs cluster:
        # TODO: Why are these attached to the launch_template role, instead of task_definition execution role?
        #           What are the differences and pros/cons of the two?
        # https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-awsmanpol.html#instance-iam-role-permissions
        self.ec2_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonEC2ContainerServiceforEC2Role"))
        ## Let the instance allow SSM Session Manager to connect to it:
        # https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-getting-started-instance-profile.html
        # https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AmazonSSMManagedEC2InstanceDefaultPolicy.html
        self.ec2_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedEC2InstanceDefaultPolicy"))

        ## For Running Commands (on container creation I think? Keeping just in case we need it later)
        self.ec2_user_data = ec2.UserData.for_linux()
        # self.ec2_user_data.add_commands()

        ## Contains the configuration information to launch an instance, and stores launch parameters
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2.LaunchTemplate.html
        self.launch_template = ec2.LaunchTemplate(
            self,
            f"{construct_id}-ASG-LaunchTemplate",
            instance_type=ec2.InstanceType(self.instance_type),
            ## Needs to be an "EcsOptimized" image to register to the cluster
            machine_image=ecs.EcsOptimizedImage.amazon_linux2(),
            # Lets Specific traffic to/from the instance:
            security_group=self.sg_container_traffic,
            user_data=self.ec2_user_data,
            role=self.ec2_role,
        )

        ## A Fleet represents a managed set of EC2 instances:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_autoscaling.AutoScalingGroup.html
        self.auto_scaling_group = autoscaling.AutoScalingGroup(
            self,
            f"{construct_id}-ASG",
            vpc=self.vpc,
            launch_template=self.launch_template,
            desired_capacity=0,
            min_capacity=0,
            max_capacity=1,
            new_instances_protected_from_scale_in=False,
        )

        ## This allows an ECS cluster to target a specific EC2 Auto Scaling Group for the placement of tasks.
        # Can ensure that instances are not prematurely terminated while there are still tasks running on them.
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.AsgCapacityProvider.html
        self.capacity_provider = ecs.AsgCapacityProvider(
            self,
            f"{construct_id}-AsgCapacityProvider",
            auto_scaling_group=self.auto_scaling_group,
            # To let me delete the stack!!:
            enable_managed_termination_protection=False,
        )
        self.ecs_cluster.add_asg_capacity_provider(self.capacity_provider)
        ## Just to populate information in the console, doesn't change the logic:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.Cluster.html#addwbrdefaultwbrcapacitywbrproviderwbrstrategydefaultcapacityproviderstrategy
        self.ecs_cluster.add_default_capacity_provider_strategy([
            ecs.CapacityProviderStrategy(capacity_provider=self.capacity_provider.capacity_provider_name)
        ])

        ## Persistent Storage:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_efs.FileSystem.html
        self.efs_file_system = efs.FileSystem(
            self,
            f"{construct_id}-efs-file-system",
            vpc=self.vpc,
            # TODO: Just for developing. Keep users minecraft worlds SAFE!!
            # (note, what's the pros/cons of RemovalPolicy.RETAIN vs RemovalPolicy.SNAPSHOT?)
            removal_policy=RemovalPolicy.DESTROY,
            security_group=self.sg_efs_traffic,
            allow_anonymous_access=False,
        )

        ## Access the Persistent Storage:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_efs.FileSystem.html#addwbraccesswbrpointid-accesspointoptions
        ## What it returns:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_efs.AccessPoint.html
        self.access_point = self.efs_file_system.add_access_point(
            f"{construct_id}-efs-access-point",
            # The task data is the only thing inside EFS:
            path="/",
            ### One of these cause the chown/chmod in the minecraft container to fail. But I'm not sure I need
            ### them? Only one container has access to one EFS, we don't need user permissions *inside* it I think...
            ### TODO: Look into this a bit more later.
            # # user/group: ec2-user
            # posix_user=efs.PosixUser(
            #     uid="1001",
            #     gid="1001",
            # ),
            # create_acl=efs.Acl(owner_gid="1001", owner_uid="1001", permissions="750"),
            # TMP root
            # posix_user=efs.PosixUser(
            #     uid="1000",
            #     gid="1000",
            # ),
            # create_acl=efs.Acl(owner_gid="1000", owner_uid="1000", permissions="750"),
        )


        ## The details of a task definition run on an EC2 cluster.
        # (Root task definition, attach containers to this)
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.TaskDefinition.html
        self.task_definition = ecs.Ec2TaskDefinition(
            self,
            f"{construct_id}-task-definition",

            # execution_role= ecs agent permissions (Permissions to pull images from ECR, BUT will automatically create one if not specified)
            # task_role= permissions for *inside* the container
        )
        self.volume_name = f"{construct_id}-efs-volume"
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.TaskDefinition.html#aws_cdk.aws_ecs.TaskDefinition.add_volume
        self.task_definition.add_volume(
            name=self.volume_name,
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.EfsVolumeConfiguration.html
            efs_volume_configuration=ecs.EfsVolumeConfiguration(
                file_system_id=self.efs_file_system.file_system_id,
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.AuthorizationConfig.html
                authorization_config=ecs.AuthorizationConfig(
                    access_point_id=self.access_point.access_point_id,
                    iam="ENABLED",
                ),
                transit_encryption="ENABLED",
            ),
        )

        # Give the task logging permissions
        # TODO: Lock this down more
        self.task_definition.add_to_task_role_policy(
            iam.PolicyStatement(
                sid="LogAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:Create*",
                    "logs:Put*",
                    "logs:Get*",
                    "logs:Describe*",
                    "logs:List*",
                ],
                resources=[f"arn:aws:logs:{self.region}:{self.account}:log-group:{construct_id}-*:*"],
            )
        )
        ## Tell the EFS side that the task can access it:
        self.efs_file_system.grant_root_access(self.task_definition.task_role)


        ## Details for add_container:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.TaskDefinition.html#addwbrcontainerid-props
        ## And what it returns:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.ContainerDefinition.html
        self.container = self.task_definition.add_container(
            f"{construct_id}-main-container",
            image=ecs.ContainerImage.from_registry(self.docker_image),
            port_mappings=[
                ecs.PortMapping(host_port=self.docker_port, container_port=self.docker_port, protocol=ecs.Protocol.TCP),
            ],
            ## Hard limit. Won't ever go above this
            # memory_limit_mib=999999999,
            ## Soft limit. Container will go down to this if under heavy load, but can go higher
            memory_reservation_mib=4*1024,
            ## Add environment variables into the container here:
            environment=container_environment,
            ## Logging, straight from:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.LogDriver.html
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="ContainerLogs",
                mode=ecs.AwsLogDriverMode.NON_BLOCKING,
                log_retention=logs.RetentionDays.ONE_WEEK,
            ),
        )
        self.container.add_mount_points(
            ecs.MountPoint(
                container_path=DATA_DIR,
                source_volume=self.volume_name,
                read_only=False,
            )
        )

        ## This creates a service using the EC2 launch type on an ECS cluster
        # TODO: If you edit this in the console, there's a way to add "placement template - one per host" to it. Can't find the CDK equivalent rn.
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.Ec2Service.html
        self.ec2_service = ecs.Ec2Service(
            self,
            f"{construct_id}-ec2-service",
            cluster=self.ecs_cluster,
            task_definition=self.task_definition,
            desired_count=0,
            circuit_breaker={
                "rollback": False # Don't keep trying to restart the container if it fails
            },
        )


        ## TODO: When getting to auto-scaling ec2 instance, this might help? Supposed to grab
        # the new IP address early:
        #   - https://github.com/aws/aws-cdk/blob/v1-main/packages/@aws-cdk-containers/ecs-service-extensions/lib/extensions/assign-public-ip/assign-public-ip.ts
        #   - https://stackoverflow.com/questions/68941663/is-there-anyway-to-determine-the-public-ip-of-a-fargate-container-before-it-beco
    

        ###########
        ## Setup Route53
        ###########
        ## The instance isn't up, use the "unknown" ip address:
        # https://www.lifewire.com/four-zero-ip-address-818384
        self.unavailable_ip = "0.0.0.0"
        # Never set TTL to 0, it's not defined in the standard
        self.unavailable_ttl = 1

        ## Add a record set that uses the base hosted zone
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_route53.RecordSet.html
        self.domain_name = f"{self.container_name_id}.{self.hosted_zone.zone_name}"
        self.dns_record = route53.RecordSet(
            self,
            f"{construct_id}-DnsRecord",
            zone=self.hosted_zone,
            record_name=self.domain_name,
            record_type=route53.RecordType.A,
            target=route53.RecordTarget.from_values(self.unavailable_ip),
            ttl=Duration.seconds(self.unavailable_ttl),
        )


        ## Lambda, count the number of connections and pass to CloudWatch Alarm
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_lambda.Function.html
        # TODO: Have one CloudWatch Alarm watch the function fails, and turn off the system
        # TODO: Hook up to a custom Cloudwatch Alarm metric, and turn off system if no connections
        #         (I keep thinking about combining the two by having it error if 0 connections, but
        #          it just feels so hacky. Plus it's good practice to get num_connections to the metric.
        #          AND you could have errors trigger at 3, and num_connections be configurable then.)
        self.lambda_count_connections = aws_lambda.Function(    # pylint: disable=invalid-name
            self,
            f"{construct_id}-lambda-count-connections",
            description="Counts the number of connections to the container, and passes it to a CloudWatch Alarm.",
            code=aws_lambda.Code.from_asset("./lambda-scale-container/"),
            handler="check_instance_connections.lambda_handler",
            runtime=aws_lambda.Runtime.PYTHON_3_12,
            timeout=Duration.seconds(30),
            environment={
                "ASG_NAME": self.auto_scaling_group.auto_scaling_group_name,
                "TASK_DEFINITION": self.task_definition.family,
            },
        )
        # Just like the other lambda, check and find the running instance:
        self.lambda_count_connections.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["autoscaling:DescribeAutoScalingGroups"],
                resources=["*"],
            )
        )
        # Give it permissions to send commands to the instance host:
        self.lambda_count_connections.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ssm:SendCommand"],
                # No clue what the instance ID will be, so lock it to the ASG:
                resources=["*"],
                conditions={
                    "StringEquals": {
                        "aws:ResourceTag/aws:autoscaling:groupName": self.auto_scaling_group.auto_scaling_group_name,
                    }
                },
            )
        )
        self.lambda_count_connections.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ssm:SendCommand"],
                resources=[f"arn:aws:ssm:{self.region}::document/AWS-RunShellScript"],
            )
        )
        self.lambda_count_connections.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ssm:GetCommandInvocation"],
                resources=[f"arn:aws:ssm:{self.region}:{self.account}:*"],
            )
        )



        ## EventBridge Rule to trigger lambda every minute, to see how many are using the container
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events.Rule.html
        self.rule_cron_count_connections = events.Rule(
            self,
            f"{construct_id}-rule-cron-count-connections",
            rule_name=f"{construct_id}-rule-cron-count-connections",
            description="Trigger Lambda every minute, to see how many are using the container",
            schedule=events.Schedule.rate(Duration.minutes(1)),
            targets=[
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events_targets.LambdaFunction.html
                targets.LambdaFunction(self.lambda_count_connections),
            ],
            # Start disabled, self.lambda_count_connections will enable it when instance starts up 
            enabled=False,
        )

        ## Lambda function to update the DNS record:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_lambda.Function.html
        self.lambda_instance_StateChange_hook = aws_lambda.Function(    # pylint: disable=invalid-name
            self,
            f"{construct_id}-lambda-instance-StateChange-hook",
            description="Triggered by ec2 changes. Starts/Stops the management logic",
            code=aws_lambda.Code.from_asset("./lambda-instance-StateChange-hook/"),
            handler="main.lambda_handler",
            runtime=aws_lambda.Runtime.PYTHON_3_12,
            timeout=Duration.seconds(30),
            environment={
                "HOSTED_ZONE_ID": self.hosted_zone.hosted_zone_id,
                "DOMAIN_NAME": self.domain_name,
                "UNAVAILABLE_IP": self.unavailable_ip,
                "UNAVAILABLE_TTL": str(self.unavailable_ttl),
                "ASG_NAME": self.auto_scaling_group.auto_scaling_group_name,
                "WATCH_INSTANCE_RULE": self.rule_cron_count_connections.rule_name,
            },
        )
        self.lambda_instance_StateChange_hook.add_to_role_policy(
            iam.PolicyStatement(
                # NOTE: these are on the list of actions that CANNOT be locked down
                #   in ANY way. You *must* use a wild card, and conditions *don't* work 🙄
                effect=iam.Effect.ALLOW,
                actions=[
                    # To get the IP of a new instance:
                    "ec2:DescribeInstances",
                    # To make sure no other instances are starting up:
                    "autoscaling:DescribeAutoScalingGroups",
                ],
                resources=["*"],
            )
        )
        ## Let it update the DNS record of this stack:
        self.lambda_instance_StateChange_hook.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["route53:ChangeResourceRecordSets"],
                resources=[self.hosted_zone.hosted_zone_arn],
            )
        )
        ## Let it enable/disable the cron rule for counting connections:
        self.lambda_instance_StateChange_hook.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["events:EnableRule", "events:DisableRule"],
                resources=[self.rule_cron_count_connections.rule_arn],
            )
        )

        ## EventBridge Rule: This is actually what hooks the Lambda to the ASG/Instance.
        #    Needed to keep the management in sync with if a container is running.
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events.Rule.html
        self.rule_instance_StateChange_hook = events.Rule(    # pylint: disable=invalid-name
            self,
            f"{construct_id}-rule-instance-StateChange-hook",
            rule_name=f"{construct_id}-rule-instance-StateChange-hook",
            description="Trigger Lambda whenever the instance state changes, to keep DNS in sync",
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events.EventPattern.html
            event_pattern=events.EventPattern(
                source=["aws.autoscaling"],
                detail_type=["EC2 Instance Launch Successful", "EC2 Instance Terminate Successful"],
                detail={
                    "AutoScalingGroupName": [self.auto_scaling_group.auto_scaling_group_name],
                },
            ),
            targets=[
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events_targets.LambdaFunction.html
                targets.LambdaFunction(self.lambda_instance_StateChange_hook),
            ],
        )





        ## Custom Metric for the number of connections
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Metric.html
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/cloudwatch/client/put_metric_data.html
        self.lambda_cron_NumConnections_metric = cloudwatch.Metric(
            namespace=construct_id,
            metric_name="Number of Connections",
            dimensions_map={
                "ContainerNameId": self.container_name_id,
            },
        )
        self.lambda_cron_NumConnections_alarm = self.lambda_cron_NumConnections_metric.create_alarm(
            # TODO
        )


        ## Grab existing metric for Lambda fail alarm
        # https://bobbyhadz.com/blog/cloudwatch-alarm-aws-cdk
        ## Something like this:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_lambda.Function.html#metricwbrerrorsprops
        self.lambda_cron_errors_metric = self.lambda_count_connections.metric_errors(
            # Default is average, I want ALL of them
            # (Default period is 5 min, I think it costs $$$ to bump it past that)
            statistic="Sum",
        )
        self.lambda_cron_errors_alarm = self.lambda_cron_errors_metric.create_alarm(
            # TODO
        )
