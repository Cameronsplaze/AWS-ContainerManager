


from aws_cdk import (
    NestedStack,
    Tags,
    aws_ec2 as ec2,
)

from ContainerManager.base_stack import ContainerManagerBaseStack

### Nested Stack info:
# https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.NestedStack.html
class SecurityGroupsNestedStack(NestedStack):
    def __init__(
            self,
            leaf_stack,
            leaf_construct_id: str,
            base_stack: ContainerManagerBaseStack,
            docker_ports_config: list,
            **kwargs
        ):
        super().__init__(leaf_stack, f"{leaf_construct_id}-SecurityGroups", **kwargs)
        ## Security Group for container traffic:
        # TODO: Since someone could theoretically break into the container,
        #        lock down traffic leaving it too.
        #        (Should be the same as VPC sg BEFORE any stacks are added. Maybe have a base SG that both use?)
        
        ## Security Group for Container's traffic:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2.SecurityGroup.html
        self.sg_container_traffic = ec2.SecurityGroup(
            self,
            "sg-container-traffic",
            vpc=base_stack.vpc,
            description=f"({leaf_construct_id}) Traffic that can go into the Container",
        )
        # Create a name of `<StackName>/sg-container-traffic` to find it easier:
        Tags.of(self.sg_container_traffic).add("Name", f"{leaf_construct_id}/sg-container-traffic")


        ## Security Group for EFS instance's traffic:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2.SecurityGroup.html
        self.sg_efs_traffic = ec2.SecurityGroup(
            self,
            "sg-efs-traffic",
            vpc=base_stack.vpc,
            description=f"({leaf_construct_id}) Traffic that can go into the EFS instance",
            # description=f"Traffic that can go into the {container.container_name} EFS instance",
        )
        # Create a name of `<StackName>/sg-efs-traffic` to find it easier:
        Tags.of(self.sg_efs_traffic).add("Name", f"{leaf_construct_id}/sg-efs-traffic")

        ## Now allow the two groups to talk to each other:
        self.sg_efs_traffic.connections.allow_from(
            self.sg_container_traffic,
            port_range=ec2.Port.tcp(2049),
            description="Allow EFS traffic IN - from container",
        )
        self.sg_container_traffic.connections.allow_from(
            # Allow efs traffic from within the Group.
            self.sg_efs_traffic,
            port_range=ec2.Port.tcp(2049),
            description="Allow EFS traffic IN - from EFS Server",
        )


        # Loop over each port and figure out what it wants:
        for port_info in docker_ports_config:
            protocol, port = list(port_info.items())[0]

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
