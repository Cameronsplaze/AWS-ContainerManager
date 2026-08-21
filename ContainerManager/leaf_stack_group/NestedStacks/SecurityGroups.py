
"""
This module contains the SecurityGroups NestedStack class.
"""

import ipaddress

from aws_cdk import (
    NestedStack,
    Tags,
    aws_ec2 as ec2,
)
from constructs import Construct


def cidr_to_peer(cidr: str) -> ec2.IPeer:
    """ `Peer.ipv4` throws on an IPv6 cidr, and vice-versa. """
    if ipaddress.ip_network(cidr).version == 6:
        return ec2.Peer.ipv6(cidr)
    return ec2.Peer.ipv4(cidr)


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
        container_ports_config: list,
        ec2_config: dict,
        **kwargs,
    ) -> None:
        super().__init__(scope, "SecurityGroupsNestedStack", **kwargs)

        ## Security Group for Instance's traffic:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2.SecurityGroup.html
        self.sg_ec2_instance_traffic = ec2.SecurityGroup(
            self,
            "SgEc2InstanceTraffic",
            vpc=vpc,
            description=f"({container_id}): Traffic for the EC2 Instance",
            # Impossible to know container will need/want:
            allow_all_outbound=True,
        )
        # Create a name of `<StackName>/sg-ec2-instance-traffic` to find it easier:
        Tags.of(self.sg_ec2_instance_traffic).add("Name", f"{leaf_construct_id}/sg-ec2-instance-traffic")
        ## Allow SSH traffic, from just the configured CIDR ranges:
        for ssh_cidr in ec2_config["SshCidrAllowed"]:
            self.sg_ec2_instance_traffic.connections.allow_from(
                cidr_to_peer(ssh_cidr),
                # Same as TCP 22:
                ec2.Port.SSH,
                description=f"Allow SSH traffic IN - from {ssh_cidr}",
            )

        ## Security Group for EFS instance's traffic:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2.SecurityGroup.html
        self.sg_efs_traffic = ec2.SecurityGroup(
            self,
            "SgEfsTraffic",
            vpc=vpc,
            description=f"({container_id}): Traffic for EFS",
            # Lock down to JUST talk with the instance and host:
            allow_all_outbound=False,
        )
        # Create a name of `<StackName>/sg-efs-traffic` to find it easier:
        Tags.of(self.sg_efs_traffic).add("Name", f"{leaf_construct_id}/sg-efs-traffic")

        ## Allow EFS to receive traffic from the instance:
        #   (sg's are stateful, so it can reply too)
        self.sg_efs_traffic.connections.allow_from(
            self.sg_ec2_instance_traffic,
            port_range=ec2.Port.tcp(2049),
            description="Allow EFS traffic IN - from ec2 instance",
        )

        # Loop over each port and figure out what it wants:
        for port_mapping in container_ports_config:
            ## Get the string "TCP" or "UDP":
            # Starts from 'Protocol.TCP'
            protocol = str(port_mapping.protocol).split(".")[1]
            ## Get the port. Both 'host_port' and 'container_port'
            #   are the same.
            port = port_mapping.host_port

            for game_cidr in ec2_config["GameCidrAllowed"]:
                self.sg_ec2_instance_traffic.connections.allow_from(
                    cidr_to_peer(game_cidr),
                    getattr(ec2.Port, protocol.lower())(port),
                    description=f"Game port: allow {protocol.lower()} traffic IN from {port} ({game_cidr})",
                )
