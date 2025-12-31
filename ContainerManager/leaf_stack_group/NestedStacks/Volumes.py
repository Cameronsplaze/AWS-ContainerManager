
"""
This module contains the Volumes NestedStack class.
"""

import hashlib

from aws_cdk import (
    NestedStack,
    Duration,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_efs as efs,
    aws_iam as iam,
    aws_cloudwatch as cloudwatch,
)
from constructs import Construct



### Nested Stack info:
# https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.NestedStack.html
class Volumes(NestedStack):
    """
    This sets up the persistent storage for the ECS container.
    """
    def __init__(
        self,
        scope: Construct,
        vpc: ec2.Vpc,
        task_definition: ecs.Ec2TaskDefinition,
        container: ecs.ContainerDefinition,
        volumes_config: list,
        sg_efs_traffic: ec2.SecurityGroup,
        **kwargs,
    ) -> None:
        super().__init__(scope, "VolumesNestedStack", **kwargs)

        self.efs_file_systems = {}
        traffic_out_metrics = {}
        ## Loop over each volume in the config:
        for volume_name, volume_info in volumes_config.items():
            if not volume_info["Type"] == "EFS":
                continue

            volume_removal_policy = RemovalPolicy.RETAIN_ON_UPDATE_OR_DELETE \
                                    if volume_info["KeepOnDelete"] else \
                                    RemovalPolicy.DESTROY

            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_efs.FileSystem.html
            efs_file_system = efs.FileSystem(
                self,
                f"Efs-{volume_name}",
                vpc=vpc,
                removal_policy=volume_removal_policy,
                security_group=sg_efs_traffic,
                allow_anonymous_access=False,
                enable_automatic_backups=volume_info["EnableBackups"],
                encrypted=True,
                ## No need to set, only in one AZ/Subnet already. If user increases that
                ## number, they probably *want* more EFS instances. There's no other reason to:
                # one_zone=True,
            )
            ## Lock down in-transit encryption:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_iam.PolicyStatement.html
            efs_file_system.add_to_resource_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.DENY,
                    # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_iam.AnyPrincipal.html
                    principals=[iam.AnyPrincipal()],
                    actions=["*"],
                    conditions={
                        "Bool": {"aws:SecureTransport": "false"},
                    },
                )
            )

            ## Setup the paths to mount in the EC2:
            self.efs_file_systems[efs_file_system] = []

            ## (NOTE: There's another grant_read_write in EcsAsg.py ec2-role.
            #         I just didn't see a way to move it here without moving the role.)

            ## EFS Traffic Out:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Metric.html
            traffic_out_metrics[f"efs_out_{volume_name}"] = cloudwatch.Metric(
                label="EFS Traffic Out",
                metric_name="DataReadIOBytes",
                namespace="AWS/EFS",
                dimensions_map={"FileSystemId": efs_file_system.file_system_id},
                period=Duration.minutes(1),
                statistic="Sum",
            )

            ### Create mounts and attach them into the CONTAINER:
            for volume_path_info in volume_info["Paths"]:
                volume_path = volume_path_info["Path"]
                self.efs_file_systems[efs_file_system].append(volume_path)
                ## Create a UNIQUE name, using the path (Removing '.' and '/' too):
                #   (Will be something like: `Efs-<Id>-<hash>`. Can't use path directly: names got too long, and prefix are all similar.)
                volume_name = efs_file_system.node.id + "-" + hashlib.md5(volume_path.encode()).hexdigest()[:8]

                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.TaskDefinition.html#aws_cdk.aws_ecs.TaskDefinition.add_volume
                task_definition.add_volume(
                    name=volume_name,
                    # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.Host.html
                    host=ecs.Host(
                        source_path=volume_path,
                    ),
                )
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.ContainerDefinition.html#addwbrmountwbrpointsmountpoints
                container.add_mount_points(
                    ecs.MountPoint(
                        container_path=volume_path,
                        source_volume=volume_name,
                        read_only=volume_path_info["ReadOnly"],
                    )
                )

        ## Get total traffic out:
        total_bytes_out = '+'.join(traffic_out_metrics.keys()) if traffic_out_metrics else "0"
        # https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/viewing_metrics_with_cloudwatch.html#ec2-cloudwatch-metrics
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.MathExpression.html
        self.bytes_out_per_second = cloudwatch.MathExpression(
            label="(EFS) Bytes OUT per Second",
            # https://repost.aws/knowledge-center/efs-monitor-cloudwatch-metrics
            # Had to add together manually, "METRICS()" wasn't behaving, and grabbing other values it shouldn't,
            expression=f"({total_bytes_out})/60",
            using_metrics=traffic_out_metrics,
            period=Duration.minutes(1),
        )
