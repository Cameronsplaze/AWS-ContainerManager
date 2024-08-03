
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
    new_config = []
    for subscription in config["AlertSubscription"]:
        if len(subscription.items()) != 1:
            raise ValueError(f"Each subscription should have only one key-value pair. Got: {subscription.items()}")
        # The new key is the protocol cdk object itself:
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

    # Check Domain.Name:
    if "Name" not in config["Domain"]:
        raise_missing_key_error("Domain.Name")
    assert isinstance(config["Domain"]["Name"], str)
    config["Domain"]["Name"] = config["Domain"]["Name"].lower()

    # Check Domain.HostedZoneId:
    config["Domain"]["HostedZoneId"] = config["Domain"].get("HostedZoneId")

def load_base_config(path: str) -> dict:
    " For fact-checking/prepping the base config file. "
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
    config["Container"]["Environment"] = {
        key: str(val) for key, val in config["Container"]["Environment"].items()
    }


def _parse_volume(config: dict) -> None:
    if "Volume" not in config:
        config["Volume"] = {}

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
    if "InstanceType" not in config["Ec2"]:
        raise_missing_key_error("Ec2.InstanceType")
    print(config["Ec2"])

def _parse_watchdog(config: dict) -> None:
    if "Watchdog" not in config:
        config["Watchdog"] = {}

    ### MinutesWithoutConnections
    if "MinutesWithoutConnections" not in config["Watchdog"]:
        config["Watchdog"]["MinutesWithoutConnections"] = 5
    assert isinstance(config["Watchdog"]["MinutesWithoutConnections"], int)        
    assert config["Watchdog"]["MinutesWithoutConnections"] >= 2, "Watchdog.MinutesWithoutConnections must be at least 2."

    ### Type
    if "Type" not in config["Watchdog"]:
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
    
    ### Type - Extra Args
    if config["Watchdog"]["Type"] == "TCP":
        if "TcpPort" not in config["Watchdog"]:
            tcp_ports = [port for port in config["Container"]["Ports"] if port.protocol == ecs.Protocol.TCP]
            # If there's more than one TCP port:
            if len(tcp_ports) != 1:
                raise_missing_key_error("Watchdog.TcpPort")
            # Both host_port and container_port are the same:
            config["Watchdog"]["TcpPort"] = tcp_ports[0].host_port
    elif config["Watchdog"]["Type"] == "UDP":
        # No extra config options needed for UDP yet:
        pass

    ### Threshold:
    if "Threshold" not in config["Watchdog"]:
        config["Watchdog"]["Threshold"] = {}


def load_leaf_config(path: str) -> dict:
    config = parse_config(path)
    _parse_container(config)
    _parse_volume(config)
    _parse_ec2(config)
    _parse_watchdog(config)
    _parse_sns(config)
    return config
