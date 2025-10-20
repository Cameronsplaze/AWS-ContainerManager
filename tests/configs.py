from dataclasses import dataclass, replace
import glob
import tempfile
import yaml

from aws_cdk import (
    Duration,
    aws_ecs as ecs,
)
from moto import mock_aws
from ContainerManager.utils.config_loader import load_base_config, load_leaf_config, _parse_config


# Define the dataclass for each config
@mock_aws # For describing the ec2_instance in the config loader:
@dataclass
class ConfigInfo:
    label: str
    config_input: dict
    expected_output: dict | None
    loader: callable

    def create_config(self):
        file_contents = yaml.safe_dump(self.config_input)
        # tempfile will create a real file, then nuke it as soon as this
        # goes out of scope:
        with tempfile.NamedTemporaryFile("w+", suffix=".yaml", delete=True) as tmp:
            tmp.write(file_contents)
            # Make sure it's written to disk
            tmp.flush()
            # Have the loader read the "fake" file:
            return self.loader(tmp.name)

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

BASE_CONFIG_LOADED = ConfigInfo(
    label="base-stack-config.yaml",
    loader=load_base_config,
    config_input=_parse_config("./base-stack-config.yaml"),
    expected_output=None, # We don't care about the output here
)

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

### CONFIGS: Collection of configs, to use in parametrize:
# Very Minimal Configs:
CONFIGS_MINIMAL = [BASE_MINIMAL, LEAF_MINIMAL]
# Configs based on real files:
CONFIGS_LOADED = [BASE_CONFIG_LOADED] + LEAF_CONFIGS_LOADED
# All valid configs:
CONFIGS_VALID = CONFIGS_MINIMAL + CONFIGS_LOADED + [BASE_VPC_MAXAZS, LEAF_CONTAINER_PORTS, LEAF_CONTAINER_ENVIRONMENT, LEAF_VOLUMES]
# All invalid configs:
CONFIGS_INVALID = []
