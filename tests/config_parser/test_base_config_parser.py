
import glob
import copy
from dataclasses import dataclass, replace
import pytest
import yaml
import schema

from aws_cdk import (
    Duration,
    aws_ecs as ecs,
)
from ContainerManager.utils.config_loader import load_base_config, load_leaf_config, _parse_config


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
        elif isinstance(v, list):
            # yield the list itself
            yield path + [list] if with_types else path
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    # recurse into each dict in the list
                    yield from flatten_keys(item, path + [i], with_types=with_types)
                else:
                    # yield the item type
                    yield path + [i, item] if with_types else path + [i]
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

    # *technically* I don't think you need to pass in fs, but it's
    # a good reminder to use fs in any test that needs to call this.
    def create_config(self, _fs, file_path="/tmp/minimal_config.yaml"):
        file_contents = yaml.safe_dump(self.config_input)
        # - open() is patched by pyfakefs (fs above), a temp filesystem.
        # - "w" is important, so new calls will override old files.
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(file_contents)
        # Have the loader read the "fake" file:
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
            'Ports': [],
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
        'Volumes': [],
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
    expected_output=LEAF_MINIMAL.expected_output | {
        "Container": LEAF_MINIMAL.expected_output["Container"] | {
            # Each port should translate to an ecs.PortMapping:
            "Ports": [ecs.PortMapping],
        }
    },
)

LEAF_CONTAINER_ENVIRONMENT = LEAF_MINIMAL.copy(
    label="LeafContainerEnvironment",
    config_input=LEAF_MINIMAL.config_input | {
        "Container": LEAF_MINIMAL.config_input["Container"] | {
            "Environment": {
                "STRING_VAR": "TRUE",
                "BOOL_VAR": True,
                "INT_VAR": 12345,
                "FLOAT_VAR": 12.345,
            },
        }
    },
    expected_output=LEAF_MINIMAL.expected_output | {
        "Container": LEAF_MINIMAL.expected_output["Container"] | {
            "Environment": {
                # Environment variables are always strings
                "STRING_VAR": str,
                "BOOL_VAR": str,
                "INT_VAR": str,
                "FLOAT_VAR": str,
            },
        }
    },
)

LEAF_VOLUMES = LEAF_MINIMAL.copy(
    label="LeafVolumes",
    config_input=LEAF_MINIMAL.config_input | {
        "Volumes": [
            # 1: To check defaults:
            {
                "Paths": [
                    {"Path": "/data"},
                ],
            },
            # 2: To check all True:
            {
                "Paths": [
                    {"Path": "/data", "ReadOnly": True},
                ],
                "EnableBackups": True,
                "KeepOnDelete": True,
            },
            # 3: To check all False:
            {
                "Paths": [
                    {"Path": "/data", "ReadOnly": False},
                ],
                "EnableBackups": False,
                "KeepOnDelete": False,
            },
            # 4: To check multiple paths:
            {
                "Paths": [
                    {"Path": "/data"},
                    {"Path": "/config"},
                ],
            },
        ],
    },
    expected_output=LEAF_MINIMAL.expected_output | {
        "Volumes": [
            {
                "Paths": [
                    {"Path": str, "ReadOnly": bool},
                ],
                "EnableBackups": bool,
                "KeepOnDelete": bool,
            },
        ],
    },
)

CONFIGS_MINIMAL = [BASE_MINIMAL, LEAF_MINIMAL]

LEAF_CONFIGS_LOADED = []
# Loop over every config in Examples (Basically `*.ya?ml`, need both extensions):
for file_path in glob.glob("./Examples/*.yaml") + glob.glob("./Examples/*.yml"):
    # _parse_config
    loaded_config = ConfigInfo(
        label=file_path.split("/")[-1],
        loader=load_leaf_config,
        config_input=_parse_config(file_path),
        expected_output=None, # We don't care about the output here
    )
    LEAF_CONFIGS_LOADED.append(loaded_config)

CONFIGS_VALID = CONFIGS_MINIMAL + LEAF_CONFIGS_LOADED + [BASE_VPC_MAXAZS, LEAF_CONTAINER_PORTS, LEAF_CONTAINER_ENVIRONMENT, LEAF_VOLUMES]
CONFIGS_INVALID = []

def _id_for_keys(config, keys):
    return f"{config.label}-" + ".".join(map(str, keys if isinstance(keys, (list, tuple)) else [keys]))

class TestConfigParser:

    @pytest.mark.parametrize("config", CONFIGS_VALID, ids=lambda s: s.label)
    def test_config_loads(self, fs, config):
        """
        Make sure the configs load without throwing.
        """
        config.create_config(fs)

    @pytest.mark.parametrize("config", CONFIGS_INVALID, ids=lambda s: s.label)
    def test_config_throws(self, fs, config):
        """
        Make sure the configs load WITH throwing.
        """
        with pytest.raises(schema.SchemaError):
            config.create_config(fs)

    CASES_DELETE_CONTENTS = [
        pytest.param(config, keys, id=_id_for_keys(config, keys))
        for config in CONFIGS_MINIMAL
        for keys in flatten_keys(config.config_input, with_types=False)
    ]
    @pytest.mark.parametrize("config,keys",CASES_DELETE_CONTENTS)
    def test_minimal_config_delete_contents(self, fs, config, keys):
        """
        Make sure the minimal configs are minimal: Delete keys one
        at a time and make sure each one throws to make sure they're
        required.
        """
        tmp_config = copy.deepcopy(config) # So we don't modify the original
        if len(keys) == 1:
            del tmp_config.config_input[keys[0]]
        else:
            del tmp_config.config_input[keys[0]][keys[1]]

        with pytest.raises(schema.SchemaError, match=f"Missing key: '{keys[-1]}'"):
            tmp_config.create_config(fs)


    CASES_RETURN_TYPES = [
        # The ID is everything but the "type" at the end:
        pytest.param(config, keys, id=_id_for_keys(config, keys[:-1]))
        for config in CONFIGS_VALID if config.expected_output is not None
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

        assert isinstance(value, expected_type), f"Expected {expected_type} but got {type(value)} for {keys} in {config.label}"


    @pytest.mark.parametrize("config", CONFIGS_VALID, ids=lambda s: s.label)
    def test_no_extra_keys_exist_in_config(self, fs, config):
        """
        Makes sure the config that is created, is exactly the same as
        `expected_output` config, i.e they're dicts with the same nested
        keys. (but possibly different values)
        """
        if config.expected_output is None:
            pytest.skip("No expected_output to compare against.")
        minimal_config = config.create_config(fs)
        # If there's a key in minimal_config that's NOT in config.expected_output,
        # it won't get updated. The dict's won't then be equal.
        minimal_config_copy = copy.deepcopy(minimal_config)
        minimal_config_copy.update(config.expected_output)
        assert minimal_config_copy == config.expected_output, "Extra keys exist in `minimal_config`."
        # Same thing, but the other direction.
        tmp_expected_output = copy.deepcopy(config.expected_output)
        tmp_expected_output.update(minimal_config)
        assert tmp_expected_output == minimal_config, "Extra keys exist in `config.expected_output`."

class TestLeafConfigVolumes():
    def test_volume_count(self, fs):
        """
        Make sure the volume count output matches the input.
        """
        # The number you ask for:
        expected_count = len(LEAF_VOLUMES.config_input["Volumes"])
        config = LEAF_VOLUMES.create_config(fs)
        # The number the schema generates:
        actual_count = len(config["Volumes"])
        assert actual_count == expected_count, f"Expected {expected_count} volumes, got {actual_count}."

class TestLeafConfigEnvironment():
    # Loop on EACH environment variable:
    @pytest.mark.parametrize(
        "input_name,input_value",
        LEAF_CONTAINER_ENVIRONMENT.config_input["Container"]["Environment"].items(),
    )
    def test_casting_variables(self, fs, input_name, input_value):
        config = LEAF_CONTAINER_ENVIRONMENT.create_config(fs)
        env = config["Container"]["Environment"]
        output_value = env[input_name]
        assert input_name in env, f"Missing environment variable {input_name}."
        assert isinstance(output_value, str), f"Environment variable {input_name} was not a string."
        # If it was a bool, it should be a ALL LOWER string. (I've either seen containers
        # be case insensitive, or expect all-lower. You can wrap it in a string if you need case.)
        if isinstance(input_value, bool):
            assert output_value in ("true", "false"), f"Bool environment variable {input_name} should become 'true' or 'false' (all lower)."
        elif isinstance(input_value, str):
            assert output_value == input_value, f"String environment variable {input_name} should stay EXACTLY same."
        elif isinstance(input_value, (int, float)):
            assert output_value == str(input_value), f"Numeric environment variable {input_name} should become its string representation."
        else:
            pytest.fail(f"Unhandled type {type(input_value)} for environment variable {input_name}.")
