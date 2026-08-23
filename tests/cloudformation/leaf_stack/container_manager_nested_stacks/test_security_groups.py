

import pytest

from tests.configs import LEAF_MINIMAL, LEAF_EC2_CIDR_ALLOWED, LEAF_MIX_CIDR_ALLOWED_PORTS, LEAF_VOLUMES


SECURITY_GROUPS_CONFIGS = LEAF_VOLUMES + [
    LEAF_MINIMAL,
    LEAF_EC2_CIDR_ALLOWED,
    LEAF_MIX_CIDR_ALLOWED_PORTS,
]


## All of these hang off `leaf_config`, which the class below parametrizes:
@pytest.fixture
def app(cdk_app, leaf_config):
    return cdk_app(leaf_config=leaf_config)

@pytest.fixture
def config(leaf_config):
    return leaf_config.create_config()

@pytest.fixture
def sg_stack(app):
    return app.container_manager_stack.sg_nested_stack

@pytest.fixture
def logical_id(sg_stack):
    """ Find constructs by their id in the template, so descriptions can change freely. """
    return lambda security_group: sg_stack.get_logical_id(security_group.node.default_child)

@pytest.fixture
def sg_properties(app, logical_id):
    security_groups = app.container_manager_sg_template.find_resources("AWS::EC2::SecurityGroup")
    return lambda security_group: security_groups[logical_id(security_group)]["Properties"]

@pytest.fixture
def instance_ingress(sg_stack, sg_properties):
    """ Everything allowed IN to the instance. (Descriptions are cosmetic, drop them). """
    properties = sg_properties(sg_stack.sg_ec2_instance_traffic)
    return [
        {key: val for key, val in rule.items() if key != "Description"}
        for rule in properties.get("SecurityGroupIngress", [])
    ]


## This class will run all it's tests per each of SECURITY_GROUPS_CONFIGS.
@pytest.mark.parametrize("leaf_config", SECURITY_GROUPS_CONFIGS, ids=lambda config: config.label)
class TestSecurityGroups():

    def test_ssh_cidr_allowed(self, instance_ingress, config):
        """ Each SshCidrAllowed CIDR should get ssh (tcp 22) opened up to it. """
        for cidr in config["Ec2"]["SshCidrAllowed"]:
            assert {"CidrIp": cidr, "IpProtocol": "tcp", "FromPort": 22, "ToPort": 22} in instance_ingress

    def test_game_cidr_allowed(self, instance_ingress, config):
        """ Each container port should get opened up to every GameCidrAllowed CIDR. """
        for port in config["Container"]["Ports"]:
            for cidr in config["Ec2"]["GameCidrAllowed"]:
                assert {
                    "CidrIp": cidr,
                    "IpProtocol": port.protocol.value.lower(),
                    "FromPort": port.host_port,
                    "ToPort": port.host_port,
                } in instance_ingress

    def test_no_other_ingress(self, instance_ingress, config):
        """ The two tests above should account for EVERY hole in the instance's firewall. """
        assert len(instance_ingress) == len(config["Ec2"]["SshCidrAllowed"]) + (
            len(config["Container"]["Ports"]) * len(config["Ec2"]["GameCidrAllowed"])
        )

    def test_efs_only_talks_to_the_instance(self, app, sg_stack, logical_id, sg_properties):
        """ The volume should ONLY be reachable by the instance, and on the NFS port. """
        sg_template = app.container_manager_sg_template
        # Only one way in, from the instance and nowhere else:
        sg_template.resource_count_is("AWS::EC2::SecurityGroupIngress", 1)
        sg_template.has_resource_properties(
            "AWS::EC2::SecurityGroupIngress",
            {
                "GroupId": {"Fn::GetAtt": [logical_id(sg_stack.sg_efs_traffic), "GroupId"]},
                "SourceSecurityGroupId": {"Fn::GetAtt": [logical_id(sg_stack.sg_ec2_instance_traffic), "GroupId"]},
                "IpProtocol": "tcp",
                "FromPort": 2049,
                "ToPort": 2049,
            },
        )
        ## And no way out. (`allow_all_outbound=False` leaves CDK's
        # "block everything" placeholder behind, and nothing else):
        efs_egress = sg_properties(sg_stack.sg_efs_traffic)["SecurityGroupEgress"]
        assert [rule["CidrIp"] for rule in efs_egress] == ["255.255.255.255/32"]
