from dataclasses import dataclass, replace
import glob
import tempfile
import yaml

from aws_cdk import (
    Duration,
    aws_ecs as ecs,
    aws_sns as sns,
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
            'HostedZoneId': "Z123456789",
            'Name': "example.com",
        },
        'Vpc': {
            'MaxAZs': 1,
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
    expected_output=BASE_MINIMAL.expected_output | {
        'Vpc': {
            'MaxAZs': 2,
        },
    },
)

BASE_ALERT_SUBSCRIPTION = BASE_MINIMAL.copy(
    label="BaseAlertSubscription",
    config_input=BASE_MINIMAL.config_input | {
        'AlertSubscription': {
            # Can be any whitespace-separated list of emails:
            'Email': "DoesNotExist1@gmail.com DoesNotExist2@gmail.com\nDoesNotExist3@gmail.com"
        },
    },
    expected_output=BASE_MINIMAL.expected_output | {
        'AlertSubscription': {
            sns.SubscriptionProtocol.EMAIL: [
                "DoesNotExist1@gmail.com",
                "DoesNotExist2@gmail.com",
                "DoesNotExist3@gmail.com",
            ],
        },
    },
)

BASE_ALERT_SUBSCRIPTION_NONE = BASE_MINIMAL.copy(
    label="BaseAlertSubscription",
    config_input=BASE_MINIMAL.config_input | {
        'AlertSubscription': {
            # If None, Nothing should exist in expected_output:
            'Email': None,
        },
    },
    expected_output=BASE_MINIMAL.expected_output | {
        'AlertSubscription': {},
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
            'Image': "hello-world:latest",
            'Ports': [],
            'Environment': {}
        },
        'Ec2': {
            'InstanceType': "m5.large",
            'MemoryInfo': {
                'SizeInMiB': int,
            },
        },
        'Watchdog': {
            'Threshold': 2000,
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
        'Volumes': {},
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
            "Ports": [
                ecs.PortMapping(
                    container_port=25565,
                    host_port=25565,
                    protocol=ecs.Protocol.TCP,
                ),
                ecs.PortMapping(
                    container_port=12345,
                    host_port=12345,
                    protocol=ecs.Protocol.UDP,
                ),
            ],
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
                "STRING_VAR": "TRUE",
                "BOOL_VAR": "true", # Bools cast to all-lower.
                "INT_VAR": "12345",
                "FLOAT_VAR": "12.345",
            },
        }
    },
)

LEAF_VOLUMES = LEAF_MINIMAL.copy(
    label="LeafVolumes",
    config_input=LEAF_MINIMAL.config_input | {
        "Volumes": {
            # 1: To check defaults:
            "Default": {
                "Paths": [
                    {"Path": "/data-default"},
                ],
            },
            # 2: To check all True:
            "AllTrue": {
                "Paths": [
                    {"Path": "/data-all-true", "ReadOnly": True},
                ],
                "EnableBackups": True,
                "KeepOnDelete": True,
            },
            # 3: To check all False:
            "AllFalse": {
                "Paths": [
                    {"Path": "/data-all-false", "ReadOnly": False},
                ],
                "EnableBackups": False,
                "KeepOnDelete": False,
            },
            # 4: To check multiple paths:
            "MultiplePaths": {
                "Paths": [
                    {"Path": "/data-1"},
                    {"Path": "/config-2"},
                ],
            },
        },
    },
    expected_output=LEAF_MINIMAL.expected_output | {
        "Volumes": {
            ## The `flatten_keys` function can't handle wildcard dict keys, so we
            # have to specify each volume by name here:
            #  (plus it's probably better to make sure the keys exist anyways)
            "Default": {
                "Paths": [
                    {"Path": "/data-default", "ReadOnly": False},
                ],
                "EnableBackups": True,
                "KeepOnDelete": True,
            },
            "AllTrue": {
                "Paths": [
                    {"Path": "/data-all-true", "ReadOnly": True},
                ],
                "EnableBackups": True,
                "KeepOnDelete": True,
            },
            "AllFalse": {
                "Paths": [
                    {"Path": "/data-all-false", "ReadOnly": False},
                ],
                "EnableBackups": False,
                "KeepOnDelete": False,
            },
            "MultiplePaths": {
                "Paths": [
                    {"Path": "/data-1", "ReadOnly": False},
                    {"Path": "/config-2", "ReadOnly": False},
                ],
                "EnableBackups": True,
                "KeepOnDelete": True,
            },
        },
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
CONFIGS_VALID = CONFIGS_MINIMAL + CONFIGS_LOADED + [
    BASE_VPC_MAXAZS,
    BASE_ALERT_SUBSCRIPTION,
    BASE_ALERT_SUBSCRIPTION_NONE,
    LEAF_CONTAINER_PORTS,
    LEAF_CONTAINER_ENVIRONMENT,
    LEAF_VOLUMES,
]
# All invalid configs:
CONFIGS_INVALID = []
