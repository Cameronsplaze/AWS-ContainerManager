
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
    aws_backup as backup,
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
        volume_config: dict,
        volume_backup_vault: backup.BackupVault,
        sg_efs_traffic: ec2.SecurityGroup,
        **kwargs,
    ) -> None:
        super().__init__(scope, "VolumesNestedStack", **kwargs)
        self.file_systems: list[dict] = []

        self.traffic_out_metrics: dict[str, cloudwatch.MathExpression] = {}
        # TODO: Major doc update on volumes. No point in multiple anymore, and removed "Type".

        # TODO: Clean up the AWS Backups stuff.

        volume_removal_policy = RemovalPolicy.RETAIN_ON_UPDATE_OR_DELETE \
                                if volume_config["KeepOnDelete"] else \
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
            # Reversed so it shows up nicely in the console:
            f"{container.container_name}-S3FilesBucket",
            ## DO NOT SET `bucket_name`, names must be unique GLOBALLY, and multiple people wanna play Minecraft.
            # bucket_name="DO NOT SET ME!!"
            removal_policy=volume_removal_policy,
            auto_delete_objects=not volume_config["KeepOnDelete"],
            enforce_ssl=True,
            versioned=True, # Required - S3 Files relies on object versions for consistency.
            lifecycle_rules=[
                ## Cap how many OLD versions of each file to keep:
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_s3.LifecycleRule.html
                s3.LifecycleRule(
                    enabled=True,
                    ## DON'T use S3 Versioning as the backup system. It creates a copy of the ENTIRE file with each change.
                    #    Even S3 Files grouping the changes per minute, it still balloons in size.
                    # noncurrent_version_expiration=Duration.days(30),
                    noncurrent_versions_to_retain=1,
                    expired_object_delete_marker=True,
                    # NOTE: The AWS Backup scan will move everything out of cheaper tiers. It's fine for Game Servers where
                    #     everything is read on start anyways, but DO NOT enable backups for Media Servers, where you won't
                    #     watch every movie/show in one sitting.
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
            "S3FilesRole",
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
            f"S3FilesFs-{container.container_name}",
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
                        size_less_than=10 * 1024 * 1024 * 1024, # 10GB
                        trigger="ON_DIRECTORY_FIRST_ACCESS",
                    ),
                ],
            ),
        )

        ## One mount target per subnet/AZ. Both EFS and S3 Files need the same ports:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_s3files.CfnMountTarget.html
        for i, subnet in enumerate(vpc.public_subnets):
            s3files.CfnMountTarget(
                self,
                f"S3FilesMountTarget-{container.container_name}-{i}",
                file_system_id=s3_files_fs.attr_file_system_id,
                subnet_id=subnet.subnet_id,
                security_groups=[sg_efs_traffic.security_group_id],
            )

        ### Create mounts between the CONTAINER and HOST (ec2):
        for volume_path_info in volume_config["Paths"]:
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
            "Paths": [path_info["Path"] for path_info in volume_config["Paths"]],
        })

        #################
        ## AWS Backups ##
        #################
        if volume_config["EnableBackups"]:
            ## Cold storage backups must be in cold storage for at LEAST 90 days. If users want them
            # that long, default to cold as long as possible since it's cheaper:
            # https://docs.aws.amazon.com/aws-backup/latest/devguide/plan-options-and-configuration.html
            # TODO: Make this a variable.
            backup_num_days = 30
            days_to_cold = Duration.days(backup_num_days-90) if backup_num_days > 90 else None

            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_iam.Role.html
            backup_role = iam.Role(
                self,
                "BackupRole",
                assumed_by=iam.ServicePrincipal("backup.amazonaws.com"),
            )
            # backup_role.add_managed_policy(
            #     # https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AWSBackupServiceRolePolicyForBackup.html
            #     iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSBackupServiceRolePolicyForBackup")
            # )
            backup_role.add_managed_policy(
                # https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AWSBackupServiceRolePolicyForS3Backup.html
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSBackupServiceRolePolicyForS3Backup")
            )
            
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_backup.BackupPlan.html
            backup_plan = backup.BackupPlan(
                self,
                "BackupPlan",
                backup_vault=volume_backup_vault,
            )
            backup_plan.add_rule(
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_backup.BackupPlanRuleProps.html
                backup.BackupPlanRule(
                    backup_vault=volume_backup_vault,
                    delete_after=Duration.days(backup_num_days),
                    move_to_cold_storage_after=days_to_cold,
                    # DO NOT enable this!! It has the same downsides as S3 Versioning (a change to a file
                    #  copies the entire file), AND is 2x more expensive.
                    enable_continuous_backup=False,
                    # # An impossible cron, so this only runs when we trigger it manually:
                    # schedule_expression=events.Schedule.cron(
                    #     minute="0", hour="0", day="31", month="2", year="1970",
                    # )
                )
            )
            backup_plan.add_selection(
                "BackupSelection",
                resources=[
                    # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_backup.BackupResource.html
                    backup.BackupResource.from_arn(s3_bucket.bucket_arn),
                ],
                role=backup_role,
            )
