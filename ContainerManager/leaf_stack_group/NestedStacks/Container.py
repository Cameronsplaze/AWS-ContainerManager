
"""
This module contains the Container NestedStack class.
"""


from aws_cdk import (
    NestedStack,
    RemovalPolicy,
    CfnOutput,
    aws_ecs as ecs,
    aws_logs as logs,
)
from constructs import Construct


### Nested Stack info:
# https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.NestedStack.html
class Container(NestedStack):
    """
    This creates the Container Definition for other stacks to
    use and add on to.
    """
    def __init__(
        self,
        scope: Construct,
        leaf_construct_id: str,
        container_id: str,
        container_config: dict,
        **kwargs
    ) -> None:
        super().__init__(scope, "ContainerNestedStack", **kwargs)
        container_id_alpha = "".join(e for e in container_id.title() if e.isalnum())

        ## The details of a task definition run on an EC2 cluster.
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.TaskDefinition.html
        self.task_definition = ecs.Ec2TaskDefinition(
            self,
            "TaskDefinition",
            # execution_role= ecs **agent** permissions (Permissions to pull images from ECR, BUT will automatically create one if not specified)
            # task_role= permissions for *inside* the container
        )

        ## Logs for the container:
        self.container_log_group = logs.LogGroup(
            self,
            "ContainerLogGroup",
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
            container_id_alpha,
            image=ecs.ContainerImage.from_registry(container_config["Image"]),
            port_mappings=container_config["Ports"],
            essential=True,
            ## Hard limit. Won't ever go above this
            # memory_limit_mib=999999999,
            ## Soft limit. Container will go down to this if under heavy load, but can go higher
            memory_reservation_mib=2*1024,
            ## Add environment variables into the container here:
            environment=container_config["Environment"],
            ## Logging, straight from:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.LogDriver.html
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="ContainerLogs",
                log_group=self.container_log_group,
            ),
        )

        ### Save the environment to Parameters:
        for key, val in container_config["Environment"].items():
            CfnOutput(self, key, value=val, description=f"[EnvVar]: {key}")
            # These are important, attach them to the base stack too:
            CfnOutput(scope, key, value=val, description=f"[EnvVar]: {key}")
