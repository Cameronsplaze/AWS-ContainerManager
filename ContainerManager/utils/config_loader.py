
"""
config_loader.py

Parses a config file, and ensures that all required keys are present.
Also modifies data to a better format CDK can digest in places.
"""

from aws_cdk import (
    aws_sns as sns,
    aws_ecs as ecs,
)

## Using this config for management, so you can have BOTH yaml and Env Vars:
# https://github.com/mkaranasou/pyaml_env
from pyaml_env import parse_config

####################
## HELPER METHODS ##
####################
def raise_missing_key_error(key: str) -> None:
    " Error telling user where to get help. "
    raise ValueError(f"Required key '{key}' missing from config. See `./ContainerManager/README.md` on writing configs")

def _parse_sns(config: dict) -> None:
    if "AlertSubscription" not in config:
        config["AlertSubscription"] = []
    assert isinstance(config["AlertSubscription"], list)
    new_config = []
    for subscription in config["AlertSubscription"]:
        if len(subscription.items()) != 1:
            raise ValueError(f"Each subscription should have only one key-value pair. Got: {subscription.items()}")
        # The new key is the protocol cdk object itself:
        # (Not doing parsing on value. Can be str if email, int if phone-#, etc.)
        protocol_str = list(subscription.keys())[0]
        protocol = getattr(sns.SubscriptionProtocol, protocol_str.upper())
        new_config.append({
            protocol: subscription[protocol_str]
        })
    config["AlertSubscription"] = new_config

#######################
## BASE CONFIG LOGIC ##
#######################
def _parse_vpc(config: dict) -> None:
    if "Vpc" not in config:
        config["Vpc"] = {}
    assert isinstance(config["Vpc"], dict)
    config["Vpc"]["MaxAZs"] = config["Vpc"].get("MaxAZs", 1)
    assert isinstance(config["Vpc"]["MaxAZs"], int)

def _parse_domain(config: dict) -> None:
    if "Domain" not in config:
        config["Domain"] = {}
    assert isinstance(config["Domain"], dict)

    # Check Domain.Name:
    if "Name" not in config["Domain"]:
        raise_missing_key_error("Domain.Name")
    assert isinstance(config["Domain"]["Name"], str)
    config["Domain"]["Name"] = config["Domain"]["Name"].lower()

    # Check Domain.HostedZoneId:
    config["Domain"]["HostedZoneId"] = config["Domain"].get("HostedZoneId")

def load_base_config(path: str) -> dict:
    " Parser/Loader for the base stack "
    config = parse_config(path)
    _parse_vpc(config)
    _parse_domain(config)
    _parse_sns(config)
    return config

#######################
## LEAF CONFIG LOGIC ##
#######################
def _parse_container(config: dict) -> None:
    if "Container" not in config:
        config["Container"] = {}
    assert isinstance(config["Container"], dict)

    ### Check Container.Image:
    if "Image" not in config["Container"]:
        raise_missing_key_error("Container.Image")
    assert isinstance(config["Container"]["Image"], str)

    ### Parse Container.Ports:
    if "Ports" not in config["Container"]:
        raise_missing_key_error("Container.Ports")
    assert isinstance(config["Container"]["Ports"], list)
    new_ports = []
    valid_protocols = ["TCP", "UDP"]
    # Loop over each port and figure out what it wants:
    for port_info in config["Container"]["Ports"]:
        protocol, port = list(port_info.items())[0]
        assert protocol.upper() in valid_protocols, f"Protocol {protocol} is not supported. Only {valid_protocols} are supported for now."
        assert isinstance(port, int)

        ### Create a list of mappings for the container:
        new_ports.append(
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.PortMapping.html
            ecs.PortMapping(
                host_port=port,
                container_port=port,
                # This will create something like: ecs.Protocol.TCP
                protocol=getattr(ecs.Protocol, protocol.upper()),
            )
        )
    config["Container"]["Ports"] = new_ports

    ### Parse Container.Environment:
    if "Environment" not in config["Container"]:
        config["Container"]["Environment"] = {}
    assert isinstance(config["Container"]["Environment"], dict)
    config["Container"]["Environment"] = {
        str(key): str(val) for key, val in config["Container"]["Environment"].items()
    }


def _parse_volume(config: dict) -> None:
    if "Volume" not in config:
        config["Volume"] = {}
    assert isinstance(config["Volume"], dict)

    ### KeepOnDelete
    if "KeepOnDelete" not in config["Volume"]:
        config["Volume"]["KeepOnDelete"] = True
    assert isinstance(config["Volume"]["KeepOnDelete"], bool)

    ### EnableBackups
    if "EnableBackups" not in config["Volume"]:
        config["Volume"]["EnableBackups"] = True
    assert isinstance(config["Volume"]["EnableBackups"], bool)

    ### Paths
    if "Paths" not in config["Volume"]:
        config["Volume"]["Paths"] = []
    assert isinstance(config["Volume"]["Paths"], list)
    for path in config["Volume"]["Paths"]:
        if "Path" not in path:
            raise_missing_key_error("Volume.Paths[*].Path")
        assert isinstance(path["Path"], str)
        if "ReadOnly" not in path:
            path["ReadOnly"] = False
        assert isinstance(path["ReadOnly"], bool)

def _parse_ec2(config: dict) -> None:
    if "Ec2" not in config:
        config["Ec2"] = {}
    assert isinstance(config["Ec2"], dict)
    if "InstanceType" not in config["Ec2"]:
        raise_missing_key_error("Ec2.InstanceType")
    assert isinstance(config["Ec2"]["InstanceType"], str)

def _parse_watchdog(config: dict) -> None:

    def _parse_watchdog_type(config: dict) -> None:
        ### Type
        if "Type" not in config["Watchdog"]:
            ## See if we can figure out the default:
            using_tcp = any([port.protocol == ecs.Protocol.TCP for port in  config["Container"]["Ports"]])
            using_udp = any([port.protocol == ecs.Protocol.UDP for port in  config["Container"]["Ports"]])
            # If you have both port types, no way to know which to use:
            if using_tcp and using_udp:
                raise_missing_key_error("Watchdog.Type")
            # If just one, default to that:
            elif using_tcp:
                config["Watchdog"]["Type"] = "TCP"
            elif using_udp:
                config["Watchdog"]["Type"] = "UDP"
            # If they don't have either, no idea what to do either:
            else:
                raise_missing_key_error("Watchdog.Type")
        config["Watchdog"]["Type"] = config["Watchdog"]["Type"].upper()
        assert config["Watchdog"]["Type"] in ["TCP", "UDP"]

    def _parse_watchdog_type_extras(config: dict) -> None:
        if config["Watchdog"]["Type"] == "TCP":
            if "TcpPort" not in config["Watchdog"]:
                tcp_ports = [port for port in config["Container"]["Ports"] if port.protocol == ecs.Protocol.TCP]
                # If there's more than one TCP port:
                if len(tcp_ports) != 1:
                    raise_missing_key_error("Watchdog.TcpPort")
                # Both host_port and container_port are the same:
                config["Watchdog"]["TcpPort"] = tcp_ports[0].host_port
            assert isinstance(config["Watchdog"]["TcpPort"], int)
        elif config["Watchdog"]["Type"] == "UDP":
            # No extra config options needed for UDP yet:
            pass

    def _parse_watchdog_minutes_without_connections(config: dict) -> None:
        if "MinutesWithoutConnections" not in config["Watchdog"]:
            config["Watchdog"]["MinutesWithoutConnections"] = 5
        assert isinstance(config["Watchdog"]["MinutesWithoutConnections"], int)
        assert config["Watchdog"]["MinutesWithoutConnections"] >= 2, "Watchdog.MinutesWithoutConnections must be at least 2."

    def _parse_watchdog_threshold(config: dict) -> None:
        if "Threshold" not in config["Watchdog"]:
            if config["Watchdog"]["Type"] == "TCP":
                config["Watchdog"]["Threshold"] = 0
            elif config["Watchdog"]["Type"] == "UDP":
                # TODO: Keep an eye on this and adjust as we get info from each game.
                #           - Valheim: No players ~0-15 packets. W/ 1 player ~5k packets
                config["Watchdog"]["Threshold"] = 32
            else:
                # No idea how you'll hit this, but future-proofing:
                raise_missing_key_error("Watchdog.Threshold")
        assert isinstance(config["Watchdog"]["Threshold"], int)

    def _parse_watchdog_instance_left_up(config: dict) -> None:
        if "InstanceLeftUp" not in config["Watchdog"]:
            config["Watchdog"]["InstanceLeftUp"] = {}
        assert isinstance(config["Watchdog"]["InstanceLeftUp"], dict)
        # DurationHours
        if "DurationHours" not in config["Watchdog"]["InstanceLeftUp"]:
            config["Watchdog"]["InstanceLeftUp"]["DurationHours"] = 8
        assert isinstance(config["Watchdog"]["InstanceLeftUp"]["DurationHours"], int)
        # ShouldStop
        if "ShouldStop" not in config["Watchdog"]["InstanceLeftUp"]:
            config["Watchdog"]["InstanceLeftUp"]["ShouldStop"] = False
        assert isinstance(config["Watchdog"]["InstanceLeftUp"]["ShouldStop"], bool)

    if "Watchdog" not in config:
        config["Watchdog"] = {}
    assert isinstance(config["Watchdog"], dict)

    ### Type / Extras
    _parse_watchdog_type(config)
    _parse_watchdog_type_extras(config)

    ### MinutesWithoutConnections
    _parse_watchdog_minutes_without_connections(config)

    ### Threshold:
    _parse_watchdog_threshold(config)

    ### InstanceLeftUp Block
    _parse_watchdog_instance_left_up(config)


def load_leaf_config(path: str) -> dict:
    " Parser/Loader for all leaf stacks "
    config = parse_config(path)
    _parse_container(config)
    _parse_volume(config)
    _parse_ec2(config)
    _parse_watchdog(config)
    _parse_sns(config)
    return config
