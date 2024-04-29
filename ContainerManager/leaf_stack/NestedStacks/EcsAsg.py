
from aws_cdk import (
    NestedStack,
    Tags,
    Duration,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_iam as iam,
    aws_sns as sns,
    aws_efs as efs,
    aws_autoscaling as autoscaling,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cloudwatch_actions,
)
from constructs import Construct


class EcsAsg(NestedStack):
    def __init__(
            self,
            scope: Construct,
            leaf_construct_id: str,
            vpc: ec2.Vpc,
            task_definition: ecs.Ec2TaskDefinition,
            instance_type: str,
            sg_container_traffic: ec2.SecurityGroup,
            ssh_key_pair: ec2.KeyPair,
            base_stack_sns_topic: sns.Topic,
            leaf_stack_sns_topic: sns.Topic,
            efs_file_system: efs.FileSystem,
            host_access_point: efs.AccessPoint,
            **kwargs,
        ):
        # super().__init__(scope, f"{leaf_construct_id}-EcsAsg", **kwargs)
        super().__init__(scope, "EcsAsgNestedStack", **kwargs)


        ## Cluster for all the games
        # This has to stay in this stack. A cluster represents a single "instance type"
        # sort of. This is the only way to tie the ASG to the ECS Service, one-to-one.
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.Cluster.html
        self.ecs_cluster = ecs.Cluster(
            self,
            "ecs-cluster",
            cluster_name=f"{leaf_construct_id}-ecs-cluster",
            vpc=vpc,
        )


        ## Permissions for inside the instance:
        self.ec2_role = iam.Role(
            self,
            "ec2-execution-role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            description="This instance's permissions, the host of the container",
        )
        ## Give it root access to the EFS:
        efs_file_system.grant_root_access(self.ec2_role)

        ## Let the instance register itself to a ecs cluster:
        # https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-awsmanpol.html#instance-iam-role-permissions
        self.ec2_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonEC2ContainerServiceforEC2Role"))
        ## Let the instance allow SSM Session Manager to connect to it:
        # https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-getting-started-instance-profile.html
        # https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AmazonSSMManagedEC2InstanceDefaultPolicy.html
        self.ec2_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedEC2InstanceDefaultPolicy"))

        ### For Running Commands on container when it starts up:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2.UserData.html
        self.ec2_user_data = ec2.UserData.for_linux() # (Can also set to python, etc. Default bash)

        ## Mount the EFS volume:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_efs-readme.html#mounting-the-file-system-using-user-data
        #  (the first few commands on that page aren't needed. Since we're a optimized ecs image, we have those packages already)
        efs_mount_point = "/mnt/efs"
        self.ec2_user_data.add_commands(
            f'mkdir -p "{efs_mount_point}"',
            # NOTE: The docs didn't have 'iam', but you get permission denied without it:
            #      (You can also mount efs directly by removing the accesspoint flag)
            # https://docs.aws.amazon.com/efs/latest/ug/mounting-access-points.html
            f'echo "{efs_file_system.file_system_id}:/ {efs_mount_point} efs defaults,tls,iam,_netdev,accesspoint={host_access_point.access_point_id} 0 0" >> /etc/fstab',
            'mount -a -t efs,nfs4 defaults',
        )

        ## Add ECS Agent Config Variables:
        # (Full list at: https://github.com/aws/amazon-ecs-agent/blob/master/README.md#environment-variables)
        # (ECS Agent config information: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-agent-config.html)
        self.ec2_user_data.add_commands(
            ## Security Flags:
            'echo "ECS_DISABLE_PRIVILEGED=true" >> /etc/ecs/ecs.config',
            ## TODO: Look into these two, if they actually make the host more secure:
            # 'echo "ECS_SELINUX_CAPABLE=true" >> /etc/ecs/ecs.config',
            # 'echo "ECS_APPARMOR_CAPABLE=true" >> /etc/ecs/ecs.config',
            ## Isn't ever on long enough to worry about cleanup anyways:
            'echo "ECS_DISABLE_IMAGE_CLEANUP=true" >> /etc/ecs/ecs.config',
        )


        ## Contains the configuration information to launch an instance, and stores launch parameters
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2.LaunchTemplate.html
        self.launch_template = ec2.LaunchTemplate(
            self,
            "ASG-LaunchTemplate",
            instance_type=ec2.InstanceType(instance_type),
            ## Needs to be an "EcsOptimized" image to register to the cluster
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.EcsOptimizedImage.html
            machine_image=ecs.EcsOptimizedImage.amazon_linux2023(),
            # Lets Specific traffic to/from the instance:
            security_group=sg_container_traffic,
            user_data=self.ec2_user_data,
            role=self.ec2_role,
            key_pair=ssh_key_pair,
        )


        ## A Fleet represents a managed set of EC2 instances:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_autoscaling.AutoScalingGroup.html
        # TODO: Looking in the console "Activity" tab, there's a way to send SNS if instance fails to start/stop.
        #       look into pushing that SNS to at least the base stack's topic.
        self.auto_scaling_group = autoscaling.AutoScalingGroup(
            self,
            "ASG",
            vpc=vpc,
            launch_template=self.launch_template,
            # desired_capacity=0,
            min_capacity=0,
            max_capacity=1,
            new_instances_protected_from_scale_in=False,
            ## Notifications:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_autoscaling.AutoScalingGroup.html#notifications
            notifications=[
                # Let base stack sns know if something goes wrong, to flag the admin:
                autoscaling.NotificationConfiguration(topic=base_stack_sns_topic, scaling_events=autoscaling.ScalingEvents.ERRORS),
                # Let users of this specific stack know the same thing:
                autoscaling.NotificationConfiguration(topic=leaf_stack_sns_topic, scaling_events=autoscaling.ScalingEvents.ERRORS),
            ],
            # Make it push number of instances to cloudwatch, so you can warn user if it's up too long:
            group_metrics=[autoscaling.GroupMetrics(
                autoscaling.GroupMetric.IN_SERVICE_INSTANCES,
            )],
        )

        ## Grab the IN_SERVICE_INSTANCES metric and load into cdk:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Metric.html
        self.metric_asg_num_instances = cloudwatch.Metric(
            metric_name="GroupInServiceInstances",
            namespace="AWS/AutoScaling",
            dimensions_map={
                "AutoScalingGroupName": self.auto_scaling_group.auto_scaling_group_name,
            },
            period=Duration.minutes(1),
        )

        ## And the alarm to flag if the instance is up too long:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Alarm.html
        duration_before_alarm = Duration.hours(6).to_minutes(), # TODO: maybe move this to a config?
        self.alarm_asg_num_instances = self.metric_asg_num_instances.create_alarm(
            self,
            "Alarm-Instance-left-up",
            alarm_name=f"{leaf_construct_id}-Alarm-Instance-left-up",
            alarm_description="To warn if the instance is up too long",
            ### This way if the period changes, this will stay the same duration:
            # Total Duration = Number of Periods * Period length... so
            # Number of Periods = Total Duration / Period length
            evaluation_periods=int(duration_before_alarm / self.metric_asg_num_instances.period.to_minutes()),
            threshold=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.MISSING,
        )
        ## Actually email admin if this is triggered:
        #   (No need to add the other sns_topic too, only admin would ever care about this.)
        #### TODO: Make the alarm message a good format
        #          (Maybe this? https://stackoverflow.com/questions/53487067/customize-alarm-message-from-aws-cloudwatch#53500349)
        self.alarm_asg_num_instances.add_alarm_action(
            cloudwatch_actions.SnsAction(base_stack_sns_topic)
        )

        ## This allows an ECS cluster to target a specific EC2 Auto Scaling Group for the placement of tasks.
        # Can ensure that instances are not prematurely terminated while there are still tasks running on them.
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.AsgCapacityProvider.html
        self.capacity_provider = ecs.AsgCapacityProvider(
            self,
            "AsgCapacityProvider",
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

        ## This creates a service using the EC2 launch type on an ECS cluster
        # TODO: If you edit this in the console, there's a way to add "placement template - one per host" to it. Can't find the CDK equivalent rn.
        #        (This might be it: https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_ecs/PlacementConstraint.html#aws_cdk.aws_ecs.PlacementConstraint.distinct_instances)
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.Ec2Service.html
        self.ec2_service = ecs.Ec2Service(
            self,
            "ec2-service",
            cluster=self.ecs_cluster,
            task_definition=task_definition,
            desired_count=0,
            circuit_breaker={
                "rollback": False # Don't keep trying to restart the container if it fails
            },
        )
