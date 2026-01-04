
"""
config_loader.py

Parses a config file, and ensures that all required keys are present.
Also modifies data to a better format CDK can digest in places.
"""


## Using pyaml_env config for management, so you can have BOTH yaml and Env Vars:
# https://github.com/mkaranasou/pyaml_env
from pyaml_env import parse_config

## Using schema for validation and modification of the config file, so
# it's easy for our app to consume it.
from schema import Schema, SchemaError
from git import Repo, exc

from .leaf_config_parser import leaf_config_schema
from .base_config_parser import base_config_schema
from .check_maturities import check_maturities

# I broke this out, to make sure the test-suite and the stack always use the same "default_value":
def _parse_config(path: str) -> dict:
    return parse_config(path, default_value=None)

def _load(path: str, schema: Schema, error_info: dict) -> dict:
    config = _parse_config(path)
    try:
        return schema.validate(config)
    except SchemaError as e:
        # Don't use schema's built-in "Schema(data, error=asdf)". It overrides the
        # message, instead of appending to it. This appends to the end of the error:
        e.add_note("")
        e.add_note(f"Local Docs: {error_info['local_docs']}")
        # Try to get the URL of the repo, to send the user to the docs:
        #  (the test suite's tmp-fs breaks here, with no access to .git)
        try:
            origin_url = Repo(".").remotes.origin.url
            repo_url = origin_url.replace("git@github.com:", "https://github.com/").replace(".git", "")
            e.add_note(f"Online Docs: {repo_url}/{error_info['online_docs']}")
        except exc.InvalidGitRepositoryError:
            pass
        e.add_note("")
        raise

def load_base_config(path: str) -> dict:
    """ Load the base stack config file and validate it against the schema. """
    error_info = {
        "online_docs": "tree/main/ContainerManager#base-stack-summary",
        "local_docs": "./ContainerManager/README.md",
    }
    schema = base_config_schema()
    return _load(path, schema, error_info)

# Default maturity to "Prod", for the test suite:
def load_leaf_config(path: str, maturity: str="Prod") -> dict:
    """ Load the leaf stack config file and validate it against the schema. """
    check_maturities(maturity)
    error_info = {
        "online_docs": "tree/main/Examples#config-file-options",
        "local_docs": "./Examples/README.md",
    }
    schema = leaf_config_schema(maturity)
    return _load(path, schema, error_info)
