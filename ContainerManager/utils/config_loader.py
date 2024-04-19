

## Using this config for management, so you can have BOTH yaml and Env Vars:
# https://github.com/mkaranasou/pyaml_env
from pyaml_env import parse_config

####################
## HELPER METHODS ##
####################
def check_missing(config: dict, required_vars: list) -> None:
    missing_vars = [x for x in required_vars if x not in config]
    if any(missing_vars):
        raise RuntimeError(f"Missing environment vars: [{', '.join(missing_vars)}]")

#######################
## BASE CONFIG LOGIC ##
#######################
def load_base_config(path: str) -> dict:
    # TODO: Parse
    return parse_config(path)

#######################
## LEAF CONFIG LOGIC ##
#######################

def parse_docker_ports(docker_ports_config: list) -> None:
    for port_info in docker_ports_config:
        ### Each port takes the format of {Protocol: Port}:
        if len(port_info) != 1:
            raise ValueError(f"Each port should have only one key-value pair. Got: {port_info}")
        protocol, port = list(port_info.items())[0]

        # Check if the protocol is valid:
        valid_protocols = ["TCP", "UDP"]
        if protocol.upper() not in valid_protocols:
            raise NotImplementedError(f"Protocol {protocol} is not supported. Only {valid_protocols} are supported for now.")
        
        # Check if the port is valid:
        if not isinstance(port, int):
            raise ValueError(f"Port {port} should be an integer.")


required_leaf_vars = [
    "InstanceType",
    "MinutesWithoutPlayers",
    "Container",
]
def load_leaf_config(path: str) -> dict:
    config = parse_config(path)

    ## Check base-level keys in the config:
    check_missing(config, required_leaf_vars)

    ## Check Container.* level keys in the config:
    required_container_vars = [
        "Image",
        "Ports",
    ]
    check_missing(config["Container"], required_container_vars)
    parse_docker_ports(config["Container"]["Ports"])

    return config

# There's also an argument for moving `sns_subscriptions` to this file, and anything else
# that both config types share in common (base and leaf configs). Then add:
#      `subscriptions = config.get("Alert Subscription", [])`
# to the sns_subscriptions.add_sns_subscriptions() method too, it'll be clear it takes a config.
