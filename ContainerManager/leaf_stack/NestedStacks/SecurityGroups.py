
"""
This module contains the SecurityGroups NestedStack class.
"""

from aws_cdk import (
    NestedStack,
    Tags,
    aws_ec2 as ec2,
)
from constructs import Construct


### Nested Stack info:
# https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.NestedStack.html
class SecurityGroups(NestedStack):
    """
    This sets up the Security Groups for everything. Broke it
    out to avoid circular imports.
    """
    def __init__(
        self,
        scope: Construct,
        leaf_construct_id: str,
        vpc: ec2.Vpc,
        container_id: str,
        docker_ports_config: list,
        **kwargs,
    ) -> None:
        super().__init__(scope, "SecurityGroupsNestedStack", **kwargs)

        ## Security Group for Container's traffic:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2.SecurityGroup.html
        self.sg_container_traffic = ec2.SecurityGroup(
            self,
            "SgContainerTraffic",
            vpc=vpc,
            description=f"({container_id}): Traffic for the Container",
            # Impossible to know container will need/want:
            allow_all_outbound=True,
        )
        # Create a name of `<StackName>/sg-container-traffic` to find it easier:
        Tags.of(self.sg_container_traffic).add("Name", f"{leaf_construct_id}/sg-container-traffic")
        ## Allow SSH traffic:
        self.sg_container_traffic.connections.allow_from(
            ec2.Peer.any_ipv4(),
            # Same as TCP 22:
            ec2.Port.SSH,
            description="Allow SSH traffic IN",
        )

        ## Security Group for EFS instance's traffic:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2.SecurityGroup.html
        self.sg_efs_traffic = ec2.SecurityGroup(
            self,
            "SgEfsTraffic",
            vpc=vpc,
            description=f"({container_id}): Traffic for the EFS instance",
            # Lock down to JUST talk with the container and host:
            allow_all_outbound=False,
        )
        # Create a name of `<StackName>/sg-efs-traffic` to find it easier:
        Tags.of(self.sg_efs_traffic).add("Name", f"{leaf_construct_id}/sg-efs-traffic")

        ## Allow EFS to receive traffic from the container:
        #   (sg's are stateful, so it can reply too)
        self.sg_efs_traffic.connections.allow_from(
            self.sg_container_traffic,
            port_range=ec2.Port.tcp(2049),
            description="Allow EFS traffic IN - from container",
        )

        # Loop over each port and figure out what it wants:
        for port_info in docker_ports_config:
            protocol, port = list(port_info.items())[0]

            self.sg_container_traffic.connections.allow_from(
                ec2.Peer.any_ipv4(),
                getattr(ec2.Port, protocol.lower())(port),
                description=f"Game port: allow {protocol.lower()} traffic IN from {port}",
            )
