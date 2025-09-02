
from dataclasses import dataclass
import pytest
import yaml
import copy
import schema

from ContainerManager.utils.config_loader import load_base_config

minimal_structure_in = {
    'Domain': {
        'HostedZoneId': "Z123456789",
        'Name': "example.com",
    },
}

minimal_structure_out = {
    'AlertSubscription': dict,
    'Domain': {
        'HostedZoneId': str,
        'Name': str,
    },
    'Vpc': {
        'MaxAZs': int,
    },
}

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

# Base and Leaf config structs
BASE = ConfigInfo(
    label="base",
    config_input=minimal_structure_in,
    expected_output=minimal_structure_out,
    loader=load_base_config,
)

# LEAF = ConfigInfo(
#     label="leaf",
#     config_input=minimal_structure_in_leaf,
#     expected_output=minimal_structure_out_leaf,
#     loader=load_leaf_config,
# )

# Instead of just two, maybe have "MIN_BASE, FULL_LEAF, etc..."
#    lets us be flexible, with what "structs" the cloudformation
#    stacks test against.
# STRUCTS = [BASE, LEAF]
STRUCTS = [BASE]


def _id_for_keys(struct, keys):
    return f"{struct.label}-" + ".".join(map(str, keys if isinstance(keys, (list, tuple)) else [keys]))

class TestBaseConfigParser:

    CASES_DELETE_CONTENTS = [
        pytest.param(struct, keys, id=_id_for_keys(struct, keys))
        for struct in STRUCTS
        for keys in flatten_keys(struct.config_input, with_types=False)
    ]
    @pytest.mark.parametrize("struct,keys",CASES_DELETE_CONTENTS)
    def test_minimal_config_delete_contents(self, fs, struct, keys):
        """
        Make sure the minimal configs are minimal: Delete keys one
        at a time and make sure each one throws.
        """
        file_path = "/tmp/minimal.yaml"
        minimal_config = struct.create_config(fs)
        if len(keys) == 1:
            del minimal_config[keys[0]]
        else:
            del minimal_config[keys[0]][keys[1]]

        file_contents = yaml.safe_dump(minimal_config)
        fs.create_file(file_path, contents=file_contents)
        with pytest.raises(schema.SchemaError, match=f"Missing key: '{keys[-1]}'"):
            struct.loader(file_path)


    CASES_RETURN_TYPES = [
        pytest.param(struct, keys, id=_id_for_keys(struct, keys[:-1]))
        for struct in STRUCTS
        for keys in flatten_keys(struct.expected_output)
    ]
    @pytest.mark.parametrize("struct,keys", CASES_RETURN_TYPES)
    def test_config_returned_types(self, fs, struct, keys):
        """
        Make sure each config-option is the right type.
        """
        expected_type = keys.pop(-1)
        value = struct.create_config(fs)
        # walk down the nested dict using the remaining keys
        for key in keys:
            value = value[key]
        # For the last item, check it's type:
        assert isinstance(value, expected_type)

    @pytest.mark.parametrize("struct", STRUCTS, ids=lambda s: s.label)
    def test_no_extra_keys_exist_in_config(self, fs, struct):
        """
        Makes sure the config that is created, is exactly the same as
        `expected_output` config, i.e they're dicts with the same nested
        keys. (but possibly different values)
        """
        minimal_config = struct.create_config(fs)
        # If there's a key in minimal_config that's NOT in minimal_structure_out,
        # it won't get updated. The dict's won't then be equal.
        minimal_config_copy = copy.deepcopy(minimal_config)
        minimal_config_copy.update(struct.expected_output)
        assert minimal_config_copy == struct.expected_output, "Extra keys exist in the minimal_config."
        # Same thing, but the other direction.
        tmp_expected_output = copy.deepcopy(struct.expected_output)
        tmp_expected_output.update(minimal_config)
        assert tmp_expected_output == minimal_config, "Extra keys exist in the minimal_structure_out."
