
"""
This module contains the Volumes NestedStack class.
"""

from aws_cdk import (
    NestedStack,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_efs as efs,
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
        sg_efs_traffic: ec2.SecurityGroup,
        **kwargs,
    ) -> None:
        super().__init__(scope, "EfsNestedStack", **kwargs)
        ## Persistent Storage:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_efs.FileSystem.html
        if volume_config["KeepOnDelete"]:
            efs_removal_policy = RemovalPolicy.RETAIN_ON_UPDATE_OR_DELETE
        else:
            efs_removal_policy = RemovalPolicy.DESTROY
        self.efs_file_system = efs.FileSystem(
            self,
            "Efs",
            vpc=vpc,
            removal_policy=efs_removal_policy,
            security_group=sg_efs_traffic,
            allow_anonymous_access=False,
            enable_automatic_backups=volume_config["EnableBackups"],
            encrypted=True,
            ## No need to set, only in one AZ/Subnet already. If user increases that
            ## number, they probably *want* more backups. There's no other reason to:
            # one_zone=True,
        )


        ## Tell the EFS side that the task can access it:
        self.efs_file_system.grant_read_write(task_definition.task_role)
        ## (NOTE: There's another grant_root_access in EcsAsg.py ec2-role.
        #         I just didn't see a way to move it here without moving the role.)

        ### Settings for ALL access points:
        ## Create ACL:
        # (From the docs, if the `path` above does not exist, you must specify this)
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_efs.AccessPointOptions.html#createacl
        ap_acl = efs.Acl(owner_gid="1000", owner_uid="1000", permissions="700")

        ### Create a access point for the host:
        ## Creating an access point:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_efs.FileSystem.html#addwbraccesswbrpointid-accesspointoptions
        ## What it returns:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_efs.AccessPoint.html
        self.host_access_point = self.efs_file_system.add_access_point("efs-access-point-host", create_acl=ap_acl, path="/")

        ### Create mounts and attach them to the container:
        for volume_info in volume_config["Paths"]:
            volume_path = volume_info["Path"]
            read_only = volume_info["ReadOnly"]
            ## Create a UNIQUE name, ID of game + (modified) path:
            #   (Will be something like: `Minecraft-data` or `Valheim-opt-valheim`)
            volume_id = f"{container.container_name}{volume_path.replace('/','-')}"
            # Another access point, for the container (each volume gets it's own):
            access_point = self.efs_file_system.add_access_point(volume_id, create_acl=ap_acl, path=volume_path)
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.TaskDefinition.html#aws_cdk.aws_ecs.TaskDefinition.add_volume
            task_definition.add_volume(
                name=volume_id,
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.EfsVolumeConfiguration.html
                efs_volume_configuration=ecs.EfsVolumeConfiguration(
                    file_system_id=self.efs_file_system.file_system_id,
                    # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.AuthorizationConfig.html
                    authorization_config=ecs.AuthorizationConfig(
                        access_point_id=access_point.access_point_id,
                        iam="ENABLED",
                    ),
                    transit_encryption="ENABLED",
                ),
            )
            container.add_mount_points(
                ecs.MountPoint(
                    container_path=volume_path,
                    source_volume=volume_id,
                    read_only=read_only,
                )
            )
