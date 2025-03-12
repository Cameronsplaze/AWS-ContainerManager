
"""
config_loader.py

Parses a config file, and ensures that all required keys are present.
Also modifies data to a better format CDK can digest in places.
"""
## Parsing for every possible config option requires a lot of statements:
# pylint: disable=too-many-statements

from aws_cdk import (
    Duration,
    RemovalPolicy,
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
        config["AlertSubscription"] = {}
    assert isinstance(config["AlertSubscription"], dict)

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
    if "HostedZoneId" not in config["Domain"]:
        raise_missing_key_error("Domain.HostedZoneId")
    assert isinstance(config["Domain"]["HostedZoneId"], str)

def load_base_config(path: str) -> dict:
    " Parser/Loader for the base stack "
    # default_value: Dependabot PR's can't read secrets. Give variables
    #    a default value since most will be blank for the synth.
    config = parse_config(path, default_value="UNDECLARED")
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
    config["Container"]["Image"] = config["Container"]["Image"].lower()

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


def _parse_volume(config: dict, maturity: str) -> None:
    if "Volumes" not in config:
        config["Volumes"] = []
    assert isinstance(config["Volumes"], list)

    ### Parse Each Volume:
    for volume in config["Volumes"]:
        ### Type
        if "Type" not in volume:
            volume["Type"] = "EFS" # Default to EFS
        volume["Type"] = volume["Type"].upper()
        assert volume["Type"] in ["EFS"] # Will support 'S3' soon!

        ## EnableBackups
        if "EnableBackups" not in volume:
            # If the maturity is prod, default to keep the data safe:
            volume["EnableBackups"] = bool(maturity == "prod")
        assert isinstance(volume["EnableBackups"], bool)

        ## KeepOnDelete
        if "KeepOnDelete" not in volume:
            # If the maturity is prod, default to keep the data safe:
            volume["KeepOnDelete"] = bool(maturity == "prod")
        assert isinstance(volume["KeepOnDelete"], bool)
        # Private var, another good excuse to turn this into a class:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_efs.FileSystem.html
        if volume["KeepOnDelete"]:
            volume["_removal_policy"] = RemovalPolicy.RETAIN_ON_UPDATE_OR_DELETE
        else:
            volume["_removal_policy"] = RemovalPolicy.DESTROY
        del volume["KeepOnDelete"]


        ## Paths
        if "Paths" not in volume:
            raise_missing_key_error("Volumes[*].Paths")
        assert isinstance(volume["Paths"], list)
        for path in volume["Paths"]:
            if "Path" not in path:
                raise_missing_key_error("Volumes[*].Paths[*].Path")
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

    def _parse_watchdog_minutes_without_connections(config: dict) -> None:
        if "MinutesWithoutConnections" not in config["Watchdog"]:
            config["Watchdog"]["MinutesWithoutConnections"] = 7
        assert isinstance(config["Watchdog"]["MinutesWithoutConnections"], int)
        assert config["Watchdog"]["MinutesWithoutConnections"] >= 2, "Watchdog.MinutesWithoutConnections must be at least 2."
        # Cast it into a duration object:
        config["Watchdog"]["MinutesWithoutConnections"] = Duration.minutes(config["Watchdog"]["MinutesWithoutConnections"])

    def _parse_watchdog_threshold(config: dict) -> None:
        if "Threshold" not in config["Watchdog"]:
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
        assert config["Watchdog"]["InstanceLeftUp"]["DurationHours"] > 0, "Watchdog.InstanceLeftUp.DurationHours must be greater than 0."
        # Cast it into a duration object:
        config["Watchdog"]["InstanceLeftUp"]["DurationHours"] = Duration.hours(config["Watchdog"]["InstanceLeftUp"]["DurationHours"])
        # ShouldStop
        if "ShouldStop" not in config["Watchdog"]["InstanceLeftUp"]:
            config["Watchdog"]["InstanceLeftUp"]["ShouldStop"] = False
        assert isinstance(config["Watchdog"]["InstanceLeftUp"]["ShouldStop"], bool)

    if "Watchdog" not in config:
        config["Watchdog"] = {}
    assert isinstance(config["Watchdog"], dict)

    ### MinutesWithoutConnections
    _parse_watchdog_minutes_without_connections(config)

    ### Threshold:
    _parse_watchdog_threshold(config)

    ### InstanceLeftUp Block
    _parse_watchdog_instance_left_up(config)

def _parse_dashboard(config: dict) -> None:
    if "Dashboard" not in config:
        config["Dashboard"] = {}
    assert isinstance(config["Dashboard"], dict)
    ### If Enabled
    if "Enabled" not in config["Dashboard"]:
        config["Dashboard"]["Enabled"] = True
    assert isinstance(config["Dashboard"]["Enabled"], bool)
    ### IntervalMinutes
    if "IntervalMinutes" not in config["Dashboard"]:
        config["Dashboard"]["IntervalMinutes"] = 30
    assert isinstance(config["Dashboard"]["IntervalMinutes"], int)
    assert config["Dashboard"]["IntervalMinutes"] > 0, "Dashboard.IntervalMinutes must be greater than 0."
    # Cast it into a duration object:
    config["Dashboard"]["IntervalMinutes"] = Duration.minutes(config["Dashboard"]["IntervalMinutes"])
    ### ShowContainerLogTimestamp
    if "ShowContainerLogTimestamp" not in config["Dashboard"]:
        config["Dashboard"]["ShowContainerLogTimestamp"] = True
    assert isinstance(config["Dashboard"]["ShowContainerLogTimestamp"], bool)

def load_leaf_config(path: str, maturity: str) -> dict:
    " Parser/Loader for all leaf stacks "
    # default_value: Dependabot PR's can't read secrets. Give variables
    #    a default value since most will be blank for the synth.
    config = parse_config(path, default_value="UNDECLARED")
    _parse_container(config)
    _parse_volume(config, maturity)
    _parse_ec2(config)
    _parse_watchdog(config)
    _parse_sns(config)
    _parse_dashboard(config)
    return config
