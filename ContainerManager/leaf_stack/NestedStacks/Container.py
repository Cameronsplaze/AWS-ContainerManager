
from aws_cdk import (
    NestedStack,
    RemovalPolicy,
    aws_ecs as ecs,
    aws_logs as logs,
)
from constructs import Construct


### Nested Stack info:
# https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.NestedStack.html
class Container(NestedStack):
    def __init__(
            self,
            scope: Construct,
            leaf_construct_id: str,
            container_name_id: str,
            docker_image: str,
            docker_environment: dict,
            docker_ports_config: list,
            **kwargs
        ):
        super().__init__(scope, "ContainerNestedStack", **kwargs)

        ## The details of a task definition run on an EC2 cluster.
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.TaskDefinition.html
        self.task_definition = ecs.Ec2TaskDefinition(
            self,
            "task-definition",

            # execution_role= ecs **agent** permissions (Permissions to pull images from ECR, BUT will automatically create one if not specified)
            # task_role= permissions for *inside* the container
        )

        # Loop over each port and figure out what it wants:
        port_mappings = []
        for port_info in docker_ports_config:
            protocol, port = list(port_info.items())[0]


            ### Create a list of mappings for the container:
            port_mappings.append(
                ecs.PortMapping(
                    host_port=port,
                    container_port=port,
                    # This will create something like: ecs.Protocol.TCP
                    protocol=getattr(ecs.Protocol, protocol.upper()),
                )
            )

        ## Logs for the container:
        self.container_log_group = logs.LogGroup(
            self,
            "container-log-group",
            log_group_name=f"/aws/ec2/{leaf_construct_id}/{self.__class__.__name__}/ContainerLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )
        ### Give the task write logging permissions:
        self.container_log_group.grant_write(self.task_definition.task_role)

        ## Details for add_container:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.TaskDefinition.html#addwbrcontainerid-props
        ## And what it returns:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.ContainerDefinition.html
        self.container = self.task_definition.add_container(
            container_name_id.title(),
            image=ecs.ContainerImage.from_registry(docker_image),
            port_mappings=port_mappings,
            ## Hard limit. Won't ever go above this
            # memory_limit_mib=999999999,
            ## Soft limit. Container will go down to this if under heavy load, but can go higher
            memory_reservation_mib=4*1024,
            ## Add environment variables into the container here:
            environment=docker_environment,
            ## Logging, straight from:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.LogDriver.html
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="ContainerLogs",
                log_group=self.container_log_group,
            ),
        )

