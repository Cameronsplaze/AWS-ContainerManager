
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
    aws_iam as iam,
    aws_cloudwatch as cloudwatch,
    aws_s3 as s3,
    aws_s3files as s3files,
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
        self.file_systems: list[dict] = []

        self.traffic_out_metrics: dict[str, cloudwatch.MathExpression] = {}
        ## Loop over each volume in the config:
        for volume_name, volume_info in volumes_config.items():
            if volume_info["Type"] == "S3":
                volume_removal_policy = RemovalPolicy.RETAIN_ON_UPDATE_OR_DELETE \
                                        if volume_info["KeepOnDelete"] else \
                                        RemovalPolicy.DESTROY


                ## (NOTE: There's a grant_read_write in EcsAsg.py ec2-role.
                #         I just didn't see a way to move it here without moving the role.)

                ## Complete S3-Files Example from docs:
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_s3files.CfnAccessPoint.html

                ## S3 Files needs a *general purpose* bucket, but it's cheapest anyways.
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_s3.Bucket.html
                FILTER_ID = "S3FilesFilter"
                s3_bucket = s3.Bucket(
                    self,
                    f"S3FilesBucket-{volume_name}",
                    ## DO NOT SET `bucket_name`, names must be unique GLOBALLY, and multiple people wanna play Minecraft.
                    # bucket_name="DO NOT SET ME!!"
                    removal_policy=volume_removal_policy,
                    auto_delete_objects=not volume_info["KeepOnDelete"],
                    enforce_ssl=True,
                    versioned=True, # Required - S3 Files relies on object versions for consistency.
                    lifecycle_rules=[
                        ## Cap how many OLD versions of each file to keep:
                        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_s3.LifecycleRule.html
                        s3.LifecycleRule(
                            # noncurrent_versions_to_retain=3, # DON'T USE THIS! We want to keep ALL versions if they're new.
                            enabled=True,
                            # TODO: Is there any reason for multiple s3 buckets now?? Think Valheim that has 2. Maybe one with versioning off, but s3 is SO cheap anyways...
                            # TODO: Make this a variable
                            noncurrent_version_expiration=Duration.days(30),
                            transitions=[
                                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_s3.Transition.html
                                s3.Transition(
                                    storage_class=s3.StorageClass.INTELLIGENT_TIERING,
                                    transition_after=Duration.days(0),
                                ),
                            ],
                        ),
                    ],
                    metrics=[
                        ## Opt into the paid metrics:
                        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_s3.BucketMetrics.html
                        s3.BucketMetrics(id=FILTER_ID),
                    ],
                )

                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_iam.Role.html
                s3_files_role = iam.Role(
                    self,
                    f"S3FilesRole-{volume_name}",
                    assumed_by=iam.ServicePrincipal("elasticfilesystem.amazonaws.com"),
                )
                s3_files_role.add_to_policy(
                    iam.PolicyStatement(
                        actions=["s3:ListBucket*"],
                        resources=[s3_bucket.bucket_arn],
                    )
                )
                s3_files_role.add_to_policy(
                    iam.PolicyStatement(
                        actions=["s3:AbortMultipartUpload", "s3:DeleteObject", "s3:GetObject*", "s3:List*", "s3:PutObject*"],
                        resources=[s3_bucket.arn_for_objects("*")],
                    )
                )
                ## EventBridge permissions: S3 Files creates rules prefixed "DO-NOT-DELETE-S3-Files"
                # to detect S3 object changes and trigger data synchronization.
                s3_files_role.add_to_policy(
                    iam.PolicyStatement(
                        actions=[
                            "events:DeleteRule", "events:DisableRule", "events:EnableRule",
                            "events:PutRule", "events:PutTargets", "events:RemoveTargets",
                        ],
                        resources=["arn:aws:events:*:*:rule/DO-NOT-DELETE-S3-Files*"],
                        conditions={"StringEquals": {"events:ManagedBy": "elasticfilesystem.amazonaws.com"}},
                    )
                )
                s3_files_role.add_to_policy(
                    iam.PolicyStatement(
                        actions=["events:DescribeRule", "events:ListRuleNamesByTarget", "events:ListRules", "events:ListTargetsByRule"],
                        resources=["arn:aws:events:*:*:rule/*"],
                    )
                )
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_s3files.CfnFileSystem.html
                s3_files_fs = s3files.CfnFileSystem(
                    self,
                    f"S3FilesFs-{volume_name}",
                    bucket=s3_bucket.bucket_arn,
                    role_arn=s3_files_role.role_arn,
                    # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_s3files.CfnFileSystem.SynchronizationConfigurationProperty.html
                    synchronization_configuration=s3files.CfnFileSystem.SynchronizationConfigurationProperty(
                        expiration_data_rules=[
                            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_s3files.CfnFileSystem.ExpirationDataRuleProperty.html
                            s3files.CfnFileSystem.ExpirationDataRuleProperty(
                                # As small as possible, to avoid costs but still have the fast file cache.
                                days_after_last_access=1,
                            ),
                        ],
                        import_data_rules=[
                            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_s3files.CfnFileSystem.ImportDataRuleProperty.html
                            s3files.CfnFileSystem.ImportDataRuleProperty(
                                prefix="",
                                ###### TODO: Make this a variable!!
                                # Make everything go through EFS by default. Media servers
                                # can lower this in their config.
                                ## TODO: Deploy the containers, and check what the largest file so far is.
                                size_less_than=1024 * 1024 * 1024 * 1024, # 1TB
                                trigger="ON_DIRECTORY_FIRST_ACCESS",
                            ),
                        ],
                    ),
                )

                # ## S3 Files (S3 + EFS) Traffic Out:
                # # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Metric.html
                # # https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-files-monitoring-cloudwatch.html
                # s3_bytes_per_min = cloudwatch.Metric(
                #     # label=f"S3 Traffic Out ({volume_name})",
                #     metric_name="BytesDownloaded",
                #     namespace="AWS/S3",
                #     dimensions_map={
                #         "BucketName": s3_bucket.bucket_name,
                #         "FilterId": FILTER_ID,
                #     },
                #     period=Duration.minutes(1),
                #     statistic="Sum",
                # )
                # efs_bytes_per_min = cloudwatch.Metric(
                #     # label=f"EFS Traffic Out ({volume_name})",
                #     metric_name="DataReadBytes",
                #     namespace="AWS/S3/Files",
                #     dimensions_map={"FileSystemId": s3_files_fs.attr_file_system_id},
                #     period=Duration.minutes(1),
                #     statistic="Sum",
                # )

                # ## Switch bytes to KiB, so it's easier for users to work with:
                # # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.MathExpression.html
                # self.traffic_out_metrics[f"s3_out_kb_{volume_name}"] = cloudwatch.MathExpression(
                #     label=f"S3 Traffic Out ({volume_name})",
                #     # https://repost.aws/knowledge-center/efs-monitor-cloudwatch-metrics
                #     expression="s3_traffic_out/1024",
                #     using_metrics={
                #         "s3_traffic_out": s3_bytes_per_min,
                #     },
                #     period=Duration.minutes(1),
                # )
                # self.traffic_out_metrics[f"efs_out_kb_{volume_name}"] = cloudwatch.MathExpression(
                #     label=f"EFS Traffic Out ({volume_name})",
                #     expression="efs_traffic_out/1024",
                #     using_metrics={
                #         "efs_traffic_out": efs_bytes_per_min,
                #     },
                #     period=Duration.minutes(1),
                # )

                ## One mount target per subnet/AZ. Both EFS and S3 Files need the same ports:
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_s3files.CfnMountTarget.html
                for i, subnet in enumerate(vpc.public_subnets):
                    s3files.CfnMountTarget(
                        self,
                        f"S3FilesMountTarget-{volume_name}-{i}",
                        file_system_id=s3_files_fs.attr_file_system_id,
                        subnet_id=subnet.subnet_id,
                        security_groups=[sg_efs_traffic.security_group_id],
                    )

                ### Create mounts between the CONTAINER and HOST (ec2):
                for volume_path_info in volume_info["Paths"]:
                    volume_path = volume_path_info["Path"]
                    ## Create a UNIQUE name, using the path (Removing '.' and '/' too):
                    #   (Will be something like: `Efs-<Id>-<hash>`. Can't use path directly: names got too long, and prefix are all similar.)
                    volume_name = s3_files_fs.node.id + "-" + hashlib.md5(volume_path.encode()).hexdigest()[:8]

                    # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.TaskDefinition.html#aws_cdk.aws_ecs.TaskDefinition.add_volume
                    task_definition.add_volume(
                        name=volume_name,
                        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.Host.html
                        host=ecs.Host(
                            # os.path.join and pathlib don't let you combine absolute paths (for some god-forsaken reason), so no benefit:
                            source_path=f"/mnt/s3files/{s3_files_fs.node.id}/{volume_path.lstrip('/')}",
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

                self.file_systems.append({
                    "Type": "S3",
                    "Bucket": s3_bucket,
                    "FileSystem": s3_files_fs,
                    "Paths": [path_info["Path"] for path_info in volume_info["Paths"]],
                })

        # ## Get total traffic out:
        # total_bytes_out = '+'.join(self.traffic_out_metrics.keys()) if self.traffic_out_metrics else "TIME_SERIES(0)"
        # # https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/viewing_metrics_with_cloudwatch.html#ec2-cloudwatch-metrics
        # # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.MathExpression.html
        # self.kb_out_per_min = cloudwatch.MathExpression(
        #     label="(Volumes) KiB OUT per Minute",
        #     # https://repost.aws/knowledge-center/efs-monitor-cloudwatch-metrics
        #     # Had to add together manually, "METRICS()" wasn't behaving, and grabbing other values it shouldn't,
        #     expression=total_bytes_out,
        #     using_metrics=self.traffic_out_metrics,
        #     period=Duration.minutes(1),
        # )
