
from dataclasses import dataclass, replace
import pytest
import yaml
import copy
import schema

from aws_cdk import (
    Duration,
    aws_ecs as ecs,
)
from ContainerManager.utils.config_loader import load_base_config, load_leaf_config


def flatten_keys(d: dict, prefix=None, with_types=True):
    """Recursively yield all key paths in a nested dict, ending in types (as lists)."""
    if prefix is None:
        prefix = []
    for k, v in d.items():
        path = prefix + [k]
        if isinstance(v, dict):
            # yield the dict itself
            yield path + [dict] if with_types else path
            # recurse deeper
            yield from flatten_keys(v, path, with_types=with_types)
        else:
            # yield key path with its type
            yield path + [v] if with_types else path

# Define the dataclass for each config
@dataclass
class ConfigInfo:
    label: str
    config_input: dict
    expected_output: dict
    loader: callable

    def create_config(self, fs):
        file_path = "/tmp/minimal_config.yaml"
        file_contents = yaml.safe_dump(self.config_input)
        fs.create_file(file_path, contents=file_contents)
        return self.loader(file_path)

    def copy(self, **changes):
        """ Return a copy of self, with `changes` applied. """
        return replace(self, **changes)

# Base and Leaf configs
BASE_MINIMAL = ConfigInfo(
    label="BaseMinimal",
    loader=load_base_config,
    config_input={
        'Domain': {
            'HostedZoneId': "Z123456789",
            'Name': "example.com",
        },
    },
    expected_output={
        'AlertSubscription': dict,
        'Domain': {
            'HostedZoneId': str,
            'Name': str,
        },
        'Vpc': {
            'MaxAZs': int,
        },
    },
)

BASE_VPC_MAXAZS = BASE_MINIMAL.copy(
    label="BaseVpcMaxAzs",
    # Add the two dicts together:
    config_input=BASE_MINIMAL.config_input | {
        'Vpc': {
            'MaxAZs': 2,
        },
    },
)


LEAF_MINIMAL = ConfigInfo(
    label="LeafMinimal",
    loader=load_leaf_config,
    config_input={
        "Ec2": {
            "InstanceType": "m5.large",
        },
        "Container": {
            "Image": "hello-world:latest",
            "Ports": [],
        },
        "Watchdog": {
            "Threshold": 2000,
        },
    },
    expected_output={
        'Container': {
            'Image': str,
            'Ports': [ecs.PortMapping],
            'Environment': {}
        },
        'Ec2': {
            'InstanceType': str,
            'MemoryInfo': {
                'SizeInMiB': int,
            },
        },
        'Watchdog': {
            'Threshold': int,
            'InstanceLeftUp': {
                'DurationHours': Duration,
                'ShouldStop': bool,
            },
            'MinutesWithoutConnections': Duration,
        },
        'Dashboard': {
            'Enabled': bool,
            'IntervalMinutes': Duration,
            'ShowContainerLogTimestamp': bool,
        },
        'Volumes': [str],
        'AlertSubscription': {},
    },
)

LEAF_CONTAINER_PORTS = LEAF_MINIMAL.copy(
    label="LeafContainerPorts",
    # This is messy, but it's the only way to keep it in-line AND
    # auto-update if LEAF_MINIMAL changes. The only key we want
    # to update IS "Ports".
    config_input=LEAF_MINIMAL.config_input | {
        # Don't override "Image", just add "Ports":
        "Container": LEAF_MINIMAL.config_input["Container"] | {
            "Ports": [
                {"TCP": 25565},
                {"UDP": 12345},
            ],
        }
    },
)

LEAF_VOLUMES = LEAF_MINIMAL.copy(
    label="LeafVolumes",
    config_input=LEAF_MINIMAL.config_input | {
        "Volumes": [
            {
                "Paths": [
                    {"Path": "/data", "ReadOnly": False},
                ],
                "EnableBackups": True,
                "KeepOnDelete": True,
            },
        ],
    },
)

# CONFIGS = [BASE_MINIMAL]
CONFIGS = [LEAF_VOLUMES]
# CONFIGS = [LEAF_MINIMAL, LEAF_CONTAINER_PORTS]

def _id_for_keys(config, keys):
    return f"{config.label}-" + ".".join(map(str, keys if isinstance(keys, (list, tuple)) else [keys]))

class TestBaseConfigParser:

    @pytest.mark.parametrize("config", CONFIGS, ids=lambda s: s.label)
    # @pytest.mark.parametrize("config", CONFIGS_VALID, ids=lambda s: s.label)
    def test_config_loads(self, fs, config):
        """
        Make sure the configs load without throwing.
        """
        config.create_config(fs)

    # @pytest.mark.parametrize("config", CONFIGS_INVALID, ids=lambda s: s.label)
    # def test_config_throws(self, fs, config):
    #     """
    #     Make sure the configs load WITH throwing.
    #     """
    #     with pytest.raises(schema.SchemaError):
    #         config.create_config(fs)

    # CASES_DELETE_CONTENTS = [
    #     pytest.param(config, keys, id=_id_for_keys(config, keys))
    #     for config in CONFIGS
    #     for keys in flatten_keys(config.config_input, with_types=False)
    # ]
    # @pytest.mark.parametrize("config,keys",CASES_DELETE_CONTENTS)
    # def test_minimal_config_delete_contents(self, fs, config, keys):
    #     """
    #     Make sure the minimal configs are minimal: Delete keys one
    #     at a time and make sure each one throws to make sure they're
    #     required.
    #     """
    #     tmp_config = copy.deepcopy(config) # So we don't modify the original
    #     if len(keys) == 1:
    #         del tmp_config.config_input[keys[0]]
    #     else:
    #         del tmp_config.config_input[keys[0]][keys[1]]

    #     with pytest.raises(schema.SchemaError, match=f"Missing key: '{keys[-1]}'"):
    #         tmp_config.create_config(fs)


    CASES_RETURN_TYPES = [
        # The ID is everything but the "type" at the end:
        pytest.param(config, keys, id=_id_for_keys(config, keys[:-1]))
        for config in CONFIGS
        for keys in flatten_keys(config.expected_output)
    ]
    @pytest.mark.parametrize("config,keys", CASES_RETURN_TYPES)
    def test_config_returned_types(self, fs, config, keys):
        """
        Make sure each config-option is the right type.
        """
        expected_type = keys.pop(-1)
        value = config.create_config(fs)
        # walk down the nested dict using the remaining keys
        for key in keys:
            value = value[key]
        ## For the last item, check it's type:
        if isinstance(expected_type, list):
            # It's a list of things:
            assert isinstance(value, list)
            for item in value:
                assert isinstance(item, expected_type[0])
        else:
            assert isinstance(value, expected_type)

    # @pytest.mark.parametrize("config", CONFIGS, ids=lambda s: s.label)
    # def test_no_extra_keys_exist_in_config(self, fs, config):
    #     """
    #     Makes sure the config that is created, is exactly the same as
    #     `expected_output` config, i.e they're dicts with the same nested
    #     keys. (but possibly different values)
    #     """
    #     minimal_config = config.create_config(fs)
    #     # If there's a key in minimal_config that's NOT in config.expected_output,
    #     # it won't get updated. The dict's won't then be equal.
    #     minimal_config_copy = copy.deepcopy(minimal_config)
    #     minimal_config_copy.update(config.expected_output)
    #     assert minimal_config_copy == config.expected_output, "Extra keys exist in `minimal_config`."
    #     # Same thing, but the other direction.
    #     tmp_expected_output = copy.deepcopy(config.expected_output)
    #     tmp_expected_output.update(minimal_config)
    #     assert tmp_expected_output == minimal_config, "Extra keys exist in `config.expected_output`."
