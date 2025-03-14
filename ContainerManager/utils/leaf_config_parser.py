"""
Leaf Config Parser

The docs for schema is at: https://github.com/keleshev/schema
"""
from schema import Schema, And, Or, Use, Optional, SchemaError
from pyaml_env import parse_config

from aws_cdk import (
    Duration,
    aws_ecs as ecs,
)

from git import Repo

### You have to keep Schema's separate, when you need an Optional dict of an Optional dict.
# (AKA with {"a": {"b": "c"}}, if you declare "a" as optional, the "b" and "c" dict won't get
# created. It'd be an empty dict instead. This below is to stop copy-pasting it in two places.
# (The default=*, and the parser itself).
leaf_instanceLeftUp_config = Schema({
    # DurationHours: Optional, returns a cdk Duration in hours.
    Optional("DurationHours",
        default=Duration.hours(8),
    ): And(int, Use(Duration.hours)),
    Optional("ShouldStop", default=False): bool,
})
leaf_instanceLeftUp_defaults = leaf_instanceLeftUp_config.validate({})

leaf_dashboard_config = Schema({
    Optional("Enabled", default=True): bool,
    Optional("IntervalMinutes",
        default=Duration.minutes(30),
    ): And(int, Use(Duration.minutes)),
    Optional("ShowContainerLogTimestamp", default=True): bool,
})
leaf_dashboard_defaults = leaf_dashboard_config.validate({})

###################
### Leaf Config ###
###################
def leaf_config_schema(maturity: str):
    return Schema({
        "Ec2": {
            "InstanceType": str,
        },
        "Container": {
            "Image": Use(str.lower),
            "Ports": [
                And(
                    # Cast the dict types to what you want:
                    {Use(str.upper): Use(int)},
                    # Assert the ONE key is either TCP or UDP:
                    {Or("TCP", "UDP", only_one=True): int},
                    # Cast it to an ecs port mapping:
                    Use(lambda info: ecs.PortMapping(
                        container_port=list(info.values())[0],
                        host_port=list(info.values())[0],
                        protocol=getattr(ecs.Protocol, list(info.keys())[0]),
                    )),
                ),
            ],
            # Key: Optional, but defaults value to empty dict if not declared:
            # Value: Either a empty dict, or a dict of strings (that casts all values to string)
            Optional("Environment", default={}): Or({Use(str): Use(str)}, {}),
        },
        Optional("Volumes", default=[]): [{
            Optional("Type", default="EFS"): And(
                Use(str.upper),
                # Add S3 as apart of the Or here when it's supported!
                Or("EFS")
            ),
            Optional("EnableBackups", default=bool(maturity == "prod")): bool,
            Optional("KeepOnDelete", default=bool(maturity == "prod")): bool,
            # List of Path Configs to save:
            "Paths": [{
                "Path": str,
                Optional("ReadOnly", default=False): bool,
            }],
        }],
        "Watchdog": {
            "Threshold": int,
            # MinutesWithoutConnections: Optional, returns a cdk Duration in minutes.
            Optional("MinutesWithoutConnections",
                default=Duration.minutes(7),
            ): And(int, Use(Duration.minutes)),
            Optional("InstanceLeftUp", default=leaf_instanceLeftUp_defaults): leaf_instanceLeftUp_config,
        },
        Optional("AlertSubscription", default={}): {
            Optional("Email"): str,
        },
        Optional("Dashboard", default=leaf_dashboard_defaults): leaf_dashboard_config,
    })

def load(path: str, maturity: str) -> dict:
    """
    Parser/Loader for all leaf stacks
    """
    # default_value: Dependabot PR's can't read secrets. Give variables
    #    a default value since most will be blank for the synth.
    leaf_config = parse_config(path, default_value="UNDECLARED")
    leaf_schema = leaf_config_schema(maturity)
    try:
        return leaf_schema.validate(leaf_config)
    except SchemaError as e:
        # Get the URL of the repo, to send the user to the docs:
        origin_url = Repo(".").remotes.origin.url
        repo_url = origin_url.replace("git@github.com:", "https://github.com/").replace(".git", "")
        # Don't use schema's built-in "Schema(data, error=asdf)". It overrides the
        # message, instead of appending to it. This appends to the end of the error:
        e.add_note(f"Online Docs: {repo_url}/tree/main/Examples#config-file-options")
        e.add_note("Local Docs: ./Examples/README.md")
        raise

if __name__ == "__main__":
    config = load("./Examples/Minecraft.java.example.yaml", "prod")
    print(config)
