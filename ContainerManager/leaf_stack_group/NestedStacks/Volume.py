
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
    aws_sns as sns,
    aws_lambda,
    aws_logs as logs,
    aws_s3 as s3,
    aws_s3files as s3files,
    aws_backup as backup,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cloudwatch_actions,
)
from constructs import Construct



### Nested Stack info:
# https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.NestedStack.html
class Volume(NestedStack):
    """
    This sets up the persistent storage for the ECS container.
    """
    def __init__(
        self,
        scope: Construct,
        container: ecs.ContainerDefinition,
        vpc: ec2.Vpc,
        task_definition: ecs.Ec2TaskDefinition,
        volume_config: dict,
        volume_backup_vault: backup.BackupVault,
        sg_efs_traffic: ec2.SecurityGroup,
        base_stack_sns_topic: sns.Topic,
        **kwargs,
    ) -> None:
        super().__init__(scope, "VolumeNestedStack", **kwargs)
        self.file_systems: list[dict] = []
        ## AsgStateChangeHook hooks this up to the spin-down event, IF backups are enabled:
        self.lambda_trigger_aws_backup: aws_lambda.Function | None = None

        # TODO: Major doc update on volumes. No point in multiple anymore, and removed "Type".

        ## No "Volume" in the config == no storage at all. Declare anything
        #   other stacks use above this.
        if not volume_config:
            return

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
                    ## DON'T use S3 Versioning as the main backup system. It creates a copy of the ENTIRE file with each change.
                    #    Even though S3 Files groups the changes per minute, it still balloons in size.
                    noncurrent_version_expiration=Duration.days(1),
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

        # TODO: Document this variable!!! Media servers can set to 0 to disable.

        ## Controls what files get pulled into the EFS cache.
        # YOU ONLY GET 10 RULES TOTAL. Only create one if they override the default.
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_s3files.CfnFileSystem.ImportDataRuleProperty.html
        s3_files_path_overrides = [
            s3files.CfnFileSystem.ImportDataRuleProperty(
                prefix=path_info['Path'].lstrip('/'),
                size_less_than=path_info["EfsCacheFileMb"] * 1024 * 1024,
                trigger="ON_DIRECTORY_FIRST_ACCESS" if path_info["EfsCacheFileMb"] > 0 else "ON_FILE_ACCESS",
            )
            for path_info in volume_config["Paths"]
            if path_info.get("EfsCacheFileMb") is not None
        ]
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
                    ## Default Rule:
                    # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_s3files.CfnFileSystem.ImportDataRuleProperty.html
                    s3files.CfnFileSystem.ImportDataRuleProperty(
                        prefix="",
                        # TODO: Start all the current containers, and see if any files exist larger than this:
                        size_less_than=64 * 1024 * 1024, # 64MiB
                        trigger="ON_DIRECTORY_FIRST_ACCESS",
                    ),
                    ## Overrides:
                    *s3_files_path_overrides,
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
            #   If you used the element index, then adding/removing a path would cause a replacement.
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
            "Bucket": s3_bucket,
            "FileSystem": s3_files_fs,
            "Paths": [path_info["Path"] for path_info in volume_config["Paths"]],
        })

        #################
        ## AWS Backups ##
        #################
        if volume_config["EnableBackups"]:
            ## The role AWS Backup itself assumes to read the bucket (NOT the lambda's role):
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_iam.Role.html
            backup_role = iam.Role(
                self,
                "BackupRole",
                assumed_by=iam.ServicePrincipal("backup.amazonaws.com"),
                description=f"Role AWS Backup assumes to snapshot the {container.container_name} bucket.",
            )
            backup_role.add_managed_policy(
                # https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AWSBackupServiceRolePolicyForS3Backup.html
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSBackupServiceRolePolicyForS3Backup")
            )

            ## Log group for the lambda function:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_logs.LogGroup.html
            self.log_group_trigger_aws_backup = logs.LogGroup(
                self,
                "LogGroupTriggerAwsBackup",
                retention=logs.RetentionDays.ONE_WEEK,
                removal_policy=RemovalPolicy.DESTROY,
                log_group_name=f"/aws/lambda/{container.container_name}-trigger-aws-backup",
            )

            ## Lambda that actually kicks off the snapshot:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_lambda.Function.html
            self.lambda_trigger_aws_backup = aws_lambda.Function(
                self,
                "TriggerAwsBackup",
                description=f"{container.container_name}-Trigger-AWS-Backup: Snapshots the volume's bucket when the container spins down.",
                code=aws_lambda.Code.from_asset("./ContainerManager/leaf_stack_group/lambda_functions/trigger_aws_backup/"),
                handler="main.lambda_handler",
                runtime=aws_lambda.Runtime.PYTHON_3_14,
                timeout=Duration.minutes(15),
                log_group=self.log_group_trigger_aws_backup,
                # vpc=DON'T put this inside the vpc. It doesn't talk to anything inside the vpc, and wouldn't have as much bandwidth.
                environment={
                    "BACKUP_VAULT_NAME": volume_backup_vault.backup_vault_name,
                    "BUCKET_ARN": s3_bucket.bucket_arn,
                    "BACKUP_ROLE_ARN": backup_role.role_arn,
                    "FILE_SYSTEM_ID": s3_files_fs.attr_file_system_id,
                    # TODO: Document this Variable:
                    "DELETE_AFTER_DAYS": str(volume_config["KeepBackupDays"]),
                },
            )
            ### Lambda Permissions:
            # Give it write to it's own log group:
            self.log_group_trigger_aws_backup.grant_write(self.lambda_trigger_aws_backup)
            # Let it start jobs in the shared vault:
            self.lambda_trigger_aws_backup.add_to_role_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["backup:StartBackupJob"],
                    resources=[volume_backup_vault.backup_vault_arn],
                )
            )
            ## `start_backup_job` hands `backup_role` over to AWS Backup, so it needs PassRole on it:
            # https://docs.aws.amazon.com/aws-backup/latest/devguide/security-considerations.html
            self.lambda_trigger_aws_backup.add_to_role_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["iam:PassRole"],
                    resources=[backup_role.role_arn],
                    conditions={"StringEquals": {"iam:PassedToService": "backup.amazonaws.com"}},
                )
            )
            ## Let it find the old object versions to clear out before snapshotting:
            self.lambda_trigger_aws_backup.add_to_role_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["s3:ListBucketVersions"],
                    resources=[s3_bucket.bucket_arn],
                )
            )
            self.lambda_trigger_aws_backup.add_to_role_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    ## NOT "s3:DeleteObject". That'd let it add delete markers to files that are
                    # still live. This only ever removes versions that are already noncurrent.
                    actions=["s3:DeleteObjectVersion"],
                    resources=[s3_bucket.arn_for_objects("*")],
                )
            )
            self.lambda_trigger_aws_backup.add_to_role_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    # NOTE: GetMetricData supports NO resource-level permissions and NO
                    #   condition keys, so the wildcard is the only option here.
                    actions=["cloudwatch:GetMetricData"],
                    resources=["*"],
                )
            )
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_lambda.Function.html#metricwbrerrorsprops
            metric_aws_backup_errors = self.lambda_trigger_aws_backup.metric_errors(
                period = Duration.minutes(1),
            )
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Alarm.html
            alarm_aws_backup_errors = metric_aws_backup_errors.create_alarm(
                self,
                "AlarmAwsBackup",
                threshold=0,
                comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
                evaluation_periods=1,
                # Missing data means instance is off:
                treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            )
            ## Moderator only, no need to tell leaf-stack:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Alarm.html#addwbralarmwbractionactions
            alarm_aws_backup_errors.add_alarm_action(
                cloudwatch_actions.SnsAction(base_stack_sns_topic)
            )
