
"""
This module contains the Volumes NestedStack class.
"""

from aws_cdk import (
    NestedStack,
    Duration,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_efs as efs,
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
        volumes_config: dict,
        sg_efs_traffic: ec2.SecurityGroup,
        **kwargs,
    ) -> None:
        super().__init__(scope, "VolumesNestedStack", **kwargs)

        ########################
        ### EFS FILE SYSTEMS ###
        ########################

        ### Settings for ALL access points:
        ## Create ACL:
        # (From the docs, if the `path` above does not exist, you must specify this)
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_efs.AccessPointOptions.html#createacl
        self.efs_ap_acl = efs.Acl(owner_gid="1000", owner_uid="1000", permissions="700")
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_efs.PosixUser.html
        posix_user = efs.PosixUser(uid="1000", gid="1000")

        self.efs_file_systems = []
        traffic_out_metrics = {}
        # i: each construct must have a different name inside the for-loop.
        for i, volume_config in enumerate(volumes_config, start=1):
            if not volume_config["Type"] == "EFS":
                continue

            volume_removal_policy = RemovalPolicy.RETAIN_ON_UPDATE_OR_DELETE \
                                    if volume_config["KeepOnDelete"] else \
                                    RemovalPolicy.DESTROY


            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_efs.FileSystem.html
            efs_file_system = efs.FileSystem(
                self,
                f"Efs-{i}",
                vpc=vpc,
                removal_policy=volume_removal_policy,
                security_group=sg_efs_traffic,
                allow_anonymous_access=False,
                enable_automatic_backups=volume_config["EnableBackups"],
                encrypted=True,
                ## No need to set, only in one AZ/Subnet already. If user increases that
                ## number, they probably *want* more EFS instances. There's no other reason to:
                # one_zone=True,
            )
            self.efs_file_systems.append(efs_file_system)

            ## Tell the EFS side that the task can access it:
            efs_file_system.grant_read_write(task_definition.task_role)
            ## (NOTE: There's another grant_root_access in EcsAsg.py ec2-role.
            #         I just didn't see a way to move it here without moving the role.)

            ## EFS Traffic Out:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Metric.html
            traffic_out_metrics[f"efs_out_{i}"] = cloudwatch.Metric(
                label="EFS Traffic Out",
                metric_name="DataReadIOBytes",
                namespace="AWS/EFS",
                dimensions_map={"FileSystemId": efs_file_system.file_system_id},
                period=Duration.minutes(1),
                statistic="Sum",
            )

            ### Create mounts and attach them into the CONTAINER:
            for volume_info in volume_config["Paths"]:
                volume_path = volume_info["Path"]
                read_only = volume_info["ReadOnly"]
                ## Create a UNIQUE name, using the (modified) path:
                #   (Will be something like: `data` for minecraft or `opt-valheim` for valheim)
                access_point_name = volume_path.strip("/").replace("/", "-")
                ## Creating an access point:
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_efs.FileSystem.html#addwbraccesswbrpointid-accesspointoptions
                ## What it returns:
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_efs.AccessPoint.html
                container_access_point = efs_file_system.add_access_point(
                    access_point_name,
                    create_acl=self.efs_ap_acl,
                    path=volume_path,
                    posix_user=posix_user,
                )

                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.TaskDefinition.html#aws_cdk.aws_ecs.TaskDefinition.add_volume
                task_definition.add_volume(
                    name=access_point_name,
                    # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.EfsVolumeConfiguration.html
                    efs_volume_configuration=ecs.EfsVolumeConfiguration(
                        file_system_id=efs_file_system.file_system_id,
                        ## root_directory: Relative to access_point already anyways, just use default:
                        # root_directory="/",
                        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.AuthorizationConfig.html
                        authorization_config=ecs.AuthorizationConfig(
                            access_point_id=container_access_point.access_point_id,
                            iam="ENABLED",
                        ),
                        transit_encryption="ENABLED",
                    ),
                )
                container.add_mount_points(
                    ecs.MountPoint(
                        container_path=volume_path,
                        source_volume=access_point_name,
                        read_only=read_only,
                    )
                )

        ## Get total traffic out:
        # https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/viewing_metrics_with_cloudwatch.html#ec2-cloudwatch-metrics
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.MathExpression.html
        self.data_out_per_second = cloudwatch.MathExpression(
            label="(EFS) Bytes OUT per Second",
            # https://repost.aws/knowledge-center/efs-monitor-cloudwatch-metrics
            # Had to add together manually, "METRICS()" wasn't behaving, and grabbing other values it shouldn't,
            expression=f"({'+'.join(traffic_out_metrics.keys())})/60",
            using_metrics=traffic_out_metrics,
            period=Duration.minutes(1),
        )
