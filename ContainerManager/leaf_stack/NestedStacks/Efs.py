
from aws_cdk import (
    NestedStack,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_efs as efs,
)



### Nested Stack info:
# https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.NestedStack.html
class EfsNestedStack(NestedStack):
    def __init__(
            self,
            leaf_stack,
            leaf_construct_id: str,
            vpc: ec2.Vpc,
            task_definition: ecs.Ec2TaskDefinition,
            container: ecs.ContainerDefinition,
            volumes_config: list,
            sg_efs_traffic: ec2.SecurityGroup,
            **kwargs
        ):
        super().__init__(leaf_stack, f"{leaf_construct_id}-EFS", **kwargs)

        ## Persistent Storage:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_efs.FileSystem.html
        self.efs_file_system = efs.FileSystem(
            self,
            "efs-file-system",
            vpc=vpc,
            # TODO: Just for developing. Keep users minecraft worlds SAFE!!
            # (note, what's the pros/cons of RemovalPolicy.RETAIN vs RemovalPolicy.SNAPSHOT?)
            removal_policy=RemovalPolicy.DESTROY,
            security_group=sg_efs_traffic,
            allow_anonymous_access=False,
        )
        ## Tell the EFS side that the task can access it:
        self.efs_file_system.grant_root_access(task_definition.task_role)

        ### Create mounts and attach them to the container:
        for volume_info in volumes_config:
            volume_path = volume_info["Path"]
            read_only = volume_info.get("ReadOnly", False)
            ## Create a unique name, take out non-alpha characters from the path:
            #   (Will be something like: `Minecraft-data`)
            volume_id = f"{container.container_name}-{''.join(filter(str.isalnum, volume_path))}"
            ## Creating an access point:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_efs.FileSystem.html#addwbraccesswbrpointid-accesspointoptions
            ## What it returns:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_efs.AccessPoint.html
            access_point = self.efs_file_system.add_access_point(
                f"efs-access-point-{volume_id}",
                # The task data is the only thing inside EFS:
                path=volume_path,
                ### One of these cause the chown/chmod in the minecraft container to fail. But I'm not sure I need
                ### them? Only one container has access to one EFS, we don't need user permissions *inside* it I think...
                ### TODO: Look into this a bit more later.
                # # user/group: ec2-user
                # posix_user=efs.PosixUser(
                #     uid="1001",
                #     gid="1001",
                # ),
                # TMP root
                # posix_user=efs.PosixUser(
                #     uid="1000",
                #     gid="1000",
                # ),
                ### Create ACL:
                # (From the docs, if the `path` above does not exist, you must specify this)
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_efs.AccessPointOptions.html#createacl
                create_acl=efs.Acl(owner_gid="1000", owner_uid="1000", permissions="750"),
            )
            volume_name = f"efs-volume-{volume_id}"
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.TaskDefinition.html#aws_cdk.aws_ecs.TaskDefinition.add_volume
            task_definition.add_volume(
                name=volume_name,
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
                    source_volume=volume_name,
                    read_only=read_only,
                )
            )
