
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


