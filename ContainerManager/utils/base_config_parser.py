"""
Base Config Parser

The docs for schema is at: https://github.com/keleshev/schema
"""
from schema import Schema, And, Or, Use, Optional, SchemaError
from pyaml_env import parse_config

from aws_cdk import (
    Duration,
    aws_ecs as ecs,
)

from git import Repo

###################
### Base Config ###
###################
def base_config_schema():
    return Schema({
        "Vpc": {
            Optional("MaxAZs", default=1): int,
            "Domain": {
                "Name": And(str, Use(str.lower)),
                "HostedZoneId": str,
            },
        },
    })

def load(path: str) -> dict:
    """
    Parser/Loader for the base stack.
    """
    # default_value: Dependabot PR's can't read secrets. Give variables
    #    a default value since most will be blank for the synth.
    base_config = parse_config(path, default_value="UNDECLARED")
    base_schema = base_config_schema()
    try:
        return base_schema.validate(base_config)
    except SchemaError as e:
        # Get the URL of the repo, to send the user to the docs:
        origin_url = Repo(".").remotes.origin.url
        repo_url = origin_url.replace("git@github.com:", "https://github.com/").replace(".git", "")
        # Don't use schema's built-in "Schema(data, error=asdf)". It overrides the
        # message, instead of appending to it. This appends to the end of the error:
        e.add_note(f"Online Docs: {repo_url}/tree/main/ContainerManager#base-stack-summary")
        e.add_note("Local Docs: ./ContainerManager/README.md")
        raise

if __name__ == "__main__":
    config = load("./base-stack-config.yaml")
    print(config)

