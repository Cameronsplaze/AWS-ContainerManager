

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

# TODO: Re-write all of this, maybe create ec2.port objects instead of passing the dicts around all over the place.
#         (And maybe do with other dicts here too)

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

    ## Make the environment variables strings:
    environment = config["Container"].get("Environment", {})
    environment = {key: str(val) for key, val in environment.items()}
    config["Container"]["Environment"] = environment

    ######################
    ### VOLUMES CONFIG ###
    ######################
    volume = config.get("Volume", {})
    if "RemovalPolicy" in volume:
        volume["RemovalPolicy"] = volume["RemovalPolicy"].upper()
    volume["EnableBackups"] = volume.get("EnableBackups", True)

    config["Volume"] = volume

    #######################
    ### WATCHDOG CONFIG ###
    #######################
    watchdog = config.get("Watchdog", {})
    if "MinutesWithoutPlayers" not in watchdog:
        watchdog["MinutesWithoutPlayers"] = 5
    assert watchdog["MinutesWithoutPlayers"] >= 2, "MinutesWithoutPlayers must be at least 2."

    if "Type" not in watchdog:
        using_tcp = any([list(x.keys())[0] == "TCP" for x in config["Container"]["Ports"]])
        using_udp = any([list(x.keys())[0] == "UDP" for x in config["Container"]["Ports"]])
        if using_tcp:
            watchdog["Type"] = "TCP"
        elif using_udp:
            watchdog["Type"] = "UDP"
        else:
            raise ValueError("Watchdog type not specified, and could not be inferred from container ports. (Add Watchdog.Type)")

    if watchdog["Type"] == "TCP":
        if "TcpPort" not in watchdog:
            if len(config["Container"]["Ports"]) != 1:
                raise ValueError("Cannot infer TCP port from multiple ports. (Add Watchdog.TcpPort)")
            watchdog["TcpPort"] = list(config["Container"]["Ports"][0].values())[0]

    elif watchdog["Type"] == "UDP":
        pass

    # Default changes depending on protocol used:
    if "Threshold" not in watchdog:
        if watchdog["Type"] == "TCP":
            watchdog["Threshold"] = 0
        elif watchdog["Type"] == "UDP":
            # TODO: Keep an eye on this and adjust as we get info from each game.
            #           - Valheim: No players ~0-15 packets. W/ 1 player ~5k packets
            watchdog["Threshold"] = 32

    config["Watchdog"] = watchdog

    return config

# There's also an argument for moving `sns_subscriptions` to this file, and anything else
# that both config types share in common (base and leaf configs). Then add:
#      `subscriptions = config.get("Alert Subscription", [])`
# to the sns_subscriptions.add_sns_subscriptions() method too, it'll be clear it takes a config.
