
"""
This module contains the EcsAsg NestedStack class.
"""

from aws_cdk import (
    NestedStack,
    Duration,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_iam as iam,
    aws_sns as sns,
    aws_efs as efs,
    aws_events as events,
    aws_events_targets as events_targets,
    aws_autoscaling as autoscaling,
    aws_cloudwatch as cloudwatch,
)
from constructs import Construct

from cdk_nag import NagSuppressions

class EcsAsg(NestedStack):
    """
    This sets up the "hardware" of the container, and the task to
    run on it.
    """
    def __init__(
        self,
        scope: Construct,
        leaf_construct_id: str,
        container_id: str,
        container_url: str,
        vpc: ec2.Vpc,
        ssh_key_pair: ec2.KeyPair,
        base_stack_sns_topic: sns.Topic,
        leaf_stack_sns_topic: sns.Topic,
        task_definition: ecs.Ec2TaskDefinition,
        ec2_config: dict,
        sg_container_traffic: ec2.SecurityGroup,
        efs_file_system: efs.FileSystem,
        host_access_point: efs.AccessPoint,
        dashboard_widgets: list[tuple[int, cloudwatch.IWidget]],
        **kwargs,
    ) -> None:
        super().__init__(scope, "EcsAsgNestedStack", **kwargs)


        ## Cluster for the the container
        # This has to stay in this stack. A cluster represents a single "instance type"
        # sort of. This is the only way to tie the ASG to the ECS Service, one-to-one.
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.Cluster.html
        self.ecs_cluster = ecs.Cluster(
            self,
            "EcsCluster",
            cluster_name=f"{leaf_construct_id}-ecs-cluster",
            vpc=vpc,
        )


        ## Permissions for inside the instance/host of the container:
        self.ec2_role = iam.Role(
            self,
            "Ec2ExecutionRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            description="The instance's permissions (HOST of the container)",
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
            'echo "ECS_SELINUX_CAPABLE=true" >> /etc/ecs/ecs.config',
            'echo "ECS_APPARMOR_CAPABLE=true" >> /etc/ecs/ecs.config',
            ## Isn't ever on long enough to worry about cleanup anyways:
            'echo "ECS_DISABLE_IMAGE_CLEANUP=true" >> /etc/ecs/ecs.config',
        )


        ## Contains the configuration information to launch an instance, and stores launch parameters
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2.LaunchTemplate.html
        self.launch_template = ec2.LaunchTemplate(
            self,
            "LaunchTemplate",
            instance_type=ec2.InstanceType(ec2_config["InstanceType"]),
            ## Needs to be an "EcsOptimized" image to register to the cluster
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.EcsOptimizedImage.html
            machine_image=ecs.EcsOptimizedImage.amazon_linux2023(),
            # Lets Specific traffic to/from the instance:
            security_group=sg_container_traffic,
            user_data=self.ec2_user_data,
            role=self.ec2_role,
            key_pair=ssh_key_pair,
            ## Console recommends to enable IMDSv2:
            http_tokens=ec2.LaunchTemplateHttpTokens.REQUIRED,
            require_imdsv2=True,
        )


        ## A Fleet represents a managed set of EC2 instances:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_autoscaling.AutoScalingGroup.html
        self.auto_scaling_group = autoscaling.AutoScalingGroup(
            self,
            "Asg",
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
            group_metrics=[
                autoscaling.GroupMetrics(
                    autoscaling.GroupMetric.IN_SERVICE_INSTANCES,
                ),
            ],
        )

        ## This allows an ECS cluster to target a specific EC2 Auto Scaling Group for the placement of tasks.
        # Can ensure that instances are not prematurely terminated while there are still tasks running on them.
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.AsgCapacityProvider.html
        self.capacity_provider = ecs.AsgCapacityProvider(
            self,
            "AsgCapacityProvider",
            auto_scaling_group=self.auto_scaling_group,
            ## To let me delete the stack!!:
            enable_managed_termination_protection=False,
            ## Since the instances don't live long, this doesn't do anything, and
            # the system is trying to spin down twice when going down.
            enable_managed_draining=False,
        )
        self.ecs_cluster.add_asg_capacity_provider(self.capacity_provider)
        ## Just to populate information in the console, doesn't change the logic:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.Cluster.html#addwbrdefaultwbrcapacitywbrproviderwbrstrategydefaultcapacityproviderstrategy
        self.ecs_cluster.add_default_capacity_provider_strategy([
            ecs.CapacityProviderStrategy(capacity_provider=self.capacity_provider.capacity_provider_name)
        ])

        ## This creates a service using the EC2 launch type on an ECS cluster
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.Ec2Service.html
        self.ec2_service = ecs.Ec2Service(
            self,
            "Ec2Service",
            cluster=self.ecs_cluster,
            task_definition=task_definition,
            desired_count=0,
            circuit_breaker={
                "rollback": False # Don't keep trying to restart the container if it fails
            },
            ### Puts each task in a particular group, on a different instance:
            ### (Not sure if we want this. Only will ever have one instance, and adds complexity)
            # placement_constraints=[ecs.PlacementConstraint.distinct_instances()],
            # placement_strategies=[ecs.PlacementStrategy.spread_across_instances()],
        )


        ##########################
        ### Notification Stuff ###
        ##########################

        ## EventBridge Rule: Send notification to user when ECS Task spins up or down:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events.Rule.html
        message = events.RuleTargetInput.from_text("\n".join([
            f"Container for '{container_id}' has started!",
            f"Connect to it at: '{container_url}'.",
        ]))
        self.rule_notify_up = events.Rule(
            self,
            "RuleNotifyUp",
            rule_name=f"{container_id}-rule-notify-up",
            description="Let user know when system finishes spinning UP",
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events.EventPattern.html
            event_pattern=events.EventPattern(
                source=["aws.ecs"],
                detail_type=["ECS Task State Change"],
                detail={
                    "clusterArn": [self.ecs_cluster.cluster_arn],
                    # You only care if the TASK starts, or the INSTANCE stops:
                    "lastStatus": ["RUNNING"],
                    "desiredStatus": ["RUNNING"],
                },
            ),
            targets=[
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events_targets.SnsTopic.html
                events_targets.SnsTopic(
                    base_stack_sns_topic,
                    message=message,
                ),
                events_targets.SnsTopic(
                    leaf_stack_sns_topic,
                    message=message,
                ),
            ],
        )

        ## Same thing, but notify user when task spins down finally:
        ##   (Can't combine with above target, since we care about different 'detail_type'.
        ##    Don't want to spam the user sadly.)
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events.Rule.html
        message = events.RuleTargetInput.from_text(f"Container for '{container_id}' has stopped.")
        self.rule_notify_down = events.Rule(
            self,
            "RuleNotifyDown",
            rule_name=f"{container_id}-rule-notify-down",
            description="Let user know when system finishes spinning down",
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events.EventPattern.html
            event_pattern=events.EventPattern(
                source=["aws.autoscaling"],
                detail_type=["EC2 Instance-terminate Lifecycle Action"],
                detail={
                    "AutoScalingGroupName": [self.auto_scaling_group.auto_scaling_group_name],
                },
            ),
            targets=[
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events_targets.SnsTopic.html
                events_targets.SnsTopic(base_stack_sns_topic, message=message),
                events_targets.SnsTopic(leaf_stack_sns_topic, message=message),
            ],
        )

        #######################
        ### Dashboard Stuff ###
        #######################
        ### Traffic In/Out Widget:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Metric.html
        traffic_in_metric = cloudwatch.Metric(
            label="Network In",
            metric_name="NetworkIn",
            namespace="AWS/EC2",
            dimensions_map={"AutoScalingGroupName": self.auto_scaling_group.auto_scaling_group_name},
        )
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Metric.html
        traffic_out_metric = cloudwatch.Metric(
            label="Network Out",
            metric_name="NetworkOut",
            namespace="AWS/EC2",
            dimensions_map={"AutoScalingGroupName": self.auto_scaling_group.auto_scaling_group_name},
        )
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.MathExpression.html
        total_traffic_metric = cloudwatch.MathExpression(
            label="Total Network Traffic",
            expression="t_in + t_out",
            using_metrics={
                "t_in": traffic_in_metric,
                "t_out": traffic_out_metric,
            },
        )

        ### Traffic PACKETS In/Out Widget:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Metric.html
        traffic_packets_in_metric = cloudwatch.Metric(
            label="Network Packets In",
            metric_name="NetworkPacketsIn",
            namespace="AWS/EC2",
            dimensions_map={"AutoScalingGroupName": self.auto_scaling_group.auto_scaling_group_name},
        )
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Metric.html
        traffic_packets_out_metric = cloudwatch.Metric(
            label="Network Packets Out",
            metric_name="NetworkPacketsOut",
            namespace="AWS/EC2",
            dimensions_map={"AutoScalingGroupName": self.auto_scaling_group.auto_scaling_group_name},
        )
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.MathExpression.html
        total_packets_metric = cloudwatch.MathExpression(
            label="Total Packets Traffic",
            expression="t_p_in + t_p_out",
            using_metrics={
                "t_p_in": traffic_packets_in_metric,
                "t_p_out": traffic_packets_out_metric,
            },
        )

        ### Put them all in a GraphWidget:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.GraphWidget.html
        traffic_widget = cloudwatch.GraphWidget(
            title="(ASG) All Network Traffic",
            # Only show up to an hour ago:
            start="-PT1H",
            height=6,
            width=12,
            left=[traffic_packets_in_metric, traffic_packets_out_metric, total_packets_metric],
            right=[traffic_in_metric, traffic_out_metric, total_traffic_metric],
            legend_position=cloudwatch.LegendPosition.RIGHT,
            period=Duration.minutes(1),
            statistic="Sum",
            ## Left and Right Y-Axis:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.YAxisProps.html
            # Because of the MetricMath in the graph, units are unknown anyways:
            left_y_axis=cloudwatch.YAxisProps(label="Traffic Packets", show_units=False),
            right_y_axis=cloudwatch.YAxisProps(label="Traffic Amount", show_units=False),
        )
        dashboard_widgets.append((6, traffic_widget))

        ### ECS Info Widget:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.Ec2Service.html#metricwbrcpuwbrutilizationprops
        cpu_utilization_metric = self.ec2_service.metric_cpu_utilization()
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.Ec2Service.html#metricwbrmemorywbrutilizationprops
        memory_utilization_metric = self.ec2_service.metric_memory_utilization()
        ### Put them all in a GraphWidget:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.GraphWidget.html
        ecs_container_graph = cloudwatch.GraphWidget(
            title="(ECS) Container Utilization",
            # Only show up to an hour ago:
            start="-PT1H",
            height=6,
            width=12,
            right=[cpu_utilization_metric, memory_utilization_metric],
            # But have both keys in the same spot, on the right:
            legend_position=cloudwatch.LegendPosition.RIGHT,
            period=Duration.minutes(1),
            statistic="Maximum",
        )
        dashboard_widgets.append((10, ecs_container_graph))

        #####################
        ### cdk_nag stuff ###
        #####################
        # Do at very end, they have to "suppress" after everything's created to work.

        NagSuppressions.add_resource_suppressions(
            self.auto_scaling_group,
            [
                # Lambda Function:
                {
                    "id": "AwsSolutions-L1",
                    "reason": "This lambda function is controlled by cdk, can't update to latest version.",
                    # "appliesTo": "N/A (Does not exist)"
                },
                # SNS Drain Hook:
                {
                    "id": "AwsSolutions-SNS2",
                    "reason": "This sns topic is controlled by cdk, can't add server-side encryption."
                    # "appliesTo": "N/A (Does not exist)"
                },
                {
                    "id": "AwsSolutions-SNS3",
                    "reason": "This sns topic is controlled by cdk, can't add ssl/tls encryption."
                    # "appliesTo": "N/A (Does not exist)"
                },
                # ASG Permissions:
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "It's flagging on the built-in auto-scaling arn. Nothing to do. (The '*' between autoScalingGroup and autoScalingGroupName.)",
                    "appliesTo": [{"regex": "/^Resource::arn:aws:autoscaling:(.*):(.*):autoScalingGroup:\\*:autoScalingGroupName/(.*)$/g"}],
                },
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "\n".join([
                        "There's a bunch of '*' permissions, but they're either only 'Describe' type, or locked down by the 'conditions' key.",
                        "(cdk code here: https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/aws-ecs/lib/drain-hook/instance-drain-hook.ts)"
                    ]),
                    "appliesTo": ["Resource::*"],
                },
                # ASG Notifications:
                {
                    "id": "AwsSolutions-AS3",
                    "reason": "\n".join([
                        "We have the important notifications on instance lifecycles, but not all.",
                        "(We tell users when it *finishes* coming up, but who cares about when it *starts* to...)"
                    ]),
                    # "appliesTo": "N/A (Does not exist)"
                },
                # ASG EBS Encryption:
                {
                    "id": "AwsSolutions-EC26",
                    "reason": "\n".join([
                        "This is the default EBS storage cdk creates and attaches to the ASG EC2 Instances.",
                        "We can create one ourselves so the default is overidden with one with encryption,",
                        "but I don't want to maintain those settings, just use the one the cdk team supports.",
                        "(This Issue will add support anyways: https://github.com/aws/aws-cdk/issues/6459)"
                    ]),
                    # "appliesTo": "N/A (Does not exist)"
                }
            ],
            apply_to_children=True,
        )
