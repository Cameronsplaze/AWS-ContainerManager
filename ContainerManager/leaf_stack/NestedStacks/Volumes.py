
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
        volumes_config: dict,
        sg_efs_traffic: ec2.SecurityGroup,
        **kwargs,
    ) -> None:
        super().__init__(scope, "EfsNestedStack", **kwargs)

        ########################
        ### EFS FILE SYSTEMS ###
        ########################

        ### Settings for ALL access points:
        ## Create ACL:
        # (From the docs, if the `path` above does not exist, you must specify this)
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_efs.AccessPointOptions.html#createacl
        self.efs_ap_acl = efs.Acl(owner_gid="1000", owner_uid="1000", permissions="700")
        self.efs_file_systems = []
        for volume_config in volumes_config:
            if not volume_config["Type"] == "EFS":
                continue

            efs_file_system = efs.FileSystem(
                self,
                "Efs",
                vpc=vpc,
                removal_policy=volume_config["_removal_policy"],
                security_group=sg_efs_traffic,
                allow_anonymous_access=False,
                enable_automatic_backups=volume_config["EnableBackups"],
                encrypted=True,
                ## No need to set, only in one AZ/Subnet already. If user increases that
                ## number, they probably *want* more backups. There's no other reason to:
                # one_zone=True,
            )
            self.efs_file_systems.append(efs_file_system)


            ## Tell the EFS side that the task can access it:
            efs_file_system.grant_read_write(task_definition.task_role)
            ## (NOTE: There's another grant_root_access in EcsAsg.py ec2-role.
            #         I just didn't see a way to move it here without moving the role.)

            ### Create mounts and attach them to the container:
            for volume_info in volume_config["Paths"]:
                volume_path = volume_info["Path"]
                read_only = volume_info["ReadOnly"]
                ## Create a UNIQUE name, ID of game + (modified) path:
                #   (Will be something like: `Minecraft-data` or `Valheim-opt-valheim`)
                volume_id = f"{container.container_name}{volume_path.replace('/','-')}"
                # Another access point, for the container (each volume gets it's own):
                access_point = efs_file_system.add_access_point(volume_id, create_acl=self.efs_ap_acl, path=volume_path)
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.TaskDefinition.html#aws_cdk.aws_ecs.TaskDefinition.add_volume
                task_definition.add_volume(
                    name=volume_id,
                    # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.EfsVolumeConfiguration.html
                    efs_volume_configuration=ecs.EfsVolumeConfiguration(
                        file_system_id=efs_file_system.file_system_id,
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
