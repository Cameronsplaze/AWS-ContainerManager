
from aws_cdk import (
    NestedStack,
    Tags,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_logs as logs,

)

from ContainerManager.base_stack import ContainerManagerBaseStack

### Nested Stack info:
# https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.NestedStack.html
class ContainerNestedStack(NestedStack):
    def __init__(
            self,
            leaf_stack,
            leaf_construct_id: str,
            base_stack: ContainerManagerBaseStack,
            container_name_id: str,
            docker_image: str,
            docker_environment: dict,
            docker_ports_config: list,
            # sg_container_traffic: ec2.SecurityGroup,
            **kwargs
        ):
        super().__init__(leaf_stack, f"{leaf_construct_id}-Container", **kwargs)
        # self.sg_container_traffic = sg_container_traffic

        ## The details of a task definition run on an EC2 cluster.
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.TaskDefinition.html
        self.task_definition = ecs.Ec2TaskDefinition(
            self,
            "task-definition",

            # execution_role= ecs **agent** permissions (Permissions to pull images from ECR, BUT will automatically create one if not specified)
            # task_role= permissions for *inside* the container
        )

        ## Security Group for container traffic:
        # TODO: Since someone could theoretically break into the container,
        #        lock down traffic leaving it too.
        #        (Should be the same as VPC sg BEFORE any stacks are added. Maybe have a base SG that both use?)
        self.sg_container_traffic = ec2.SecurityGroup(
            self,
            "sg-container-traffic",
            vpc=base_stack.vpc,
            description="Traffic that can go into the container",
        )
        # Create a name of `<StackName>/<ClassName>/sg-container-traffic` to find it easier:
        Tags.of(self.sg_container_traffic).add("Name", f"{leaf_construct_id}/{self.__class__.__name__}/sg-container-traffic")


        # Loop over each port and figure out what it wants:
        port_mappings = []
        for port_info in docker_ports_config:
            ### Make sure it's correct:
            if len(port_info) != 1:
                raise ValueError(f"Each port should have only one key-value pair. Got: {port_info}")
            protocol, port = list(port_info.items())[0]
            if protocol.lower() not in ["tcp", "udp"]:
                raise NotImplementedError(f"Protocol {protocol} is not supported. Only TCP and UDP are supported for now.")

            ### Create a list of mappings for the container:
            port_mappings.append(
                ecs.PortMapping(
                    host_port=port,
                    container_port=port,
                    # This will create something like: ecs.Protocol.TCP
                    protocol=getattr(ecs.Protocol, protocol.upper()),
                )
            )

            ### Open up the same ports on the "firewall" vpc:
            base_stack.sg_vpc_traffic.connections.allow_from(
                ec2.Peer.any_ipv4(),
                ## Dynamically use tcp or udp from:
                # This will create something like: ec2.Port.tcp(25565)
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2.Port.html
                getattr(ec2.Port, protocol.lower())(port),
                description="Game port to allow traffic IN from",
            )
            self.sg_container_traffic.connections.allow_from(
                ec2.Peer.any_ipv4(),           # <---- TODO: Is there a way to say "from outside vpc only"? The sg_vpc_traffic doesn't do it.
                # base_stack.sg_vpc_traffic,
                getattr(ec2.Port, protocol.lower())(port),
                description="Game port to open traffic IN from",
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

