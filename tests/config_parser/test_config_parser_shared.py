

import copy
import pytest
import schema


from tests.configs import (
    CONFIGS_VALID,
    CONFIGS_INVALID,
    CONFIGS_MINIMAL,
)

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



def _id_for_keys(config, keys):
    return f"{config.label}-" + ".".join(map(str, keys if isinstance(keys, (list, tuple)) else [keys]))

class TestConfigParser:

    @pytest.mark.parametrize("config", CONFIGS_VALID, ids=lambda s: s.label)
    def test_config_loads(self, config):
        """
        Make sure the configs load without throwing.
        """
        config.create_config()

    @pytest.mark.parametrize("config", CONFIGS_INVALID, ids=lambda s: s.label)
    def test_config_throws(self, config):
        """
        Make sure the configs load WITH throwing.
        """
        with pytest.raises(schema.SchemaError):
            config.create_config()

    CASES_DELETE_CONTENTS = [
        pytest.param(config, keys, id=_id_for_keys(config, keys))
        for config in CONFIGS_MINIMAL
        for keys in flatten_keys(config.config_input, with_types=False)
    ]
    @pytest.mark.parametrize("config,keys",CASES_DELETE_CONTENTS)
    def test_minimal_config_delete_contents(self, config, keys):
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
            tmp_config.create_config()


    CASES_RETURN_TYPES = [
        # The ID is everything but the "type" at the end:
        pytest.param(config, keys, id=_id_for_keys(config, keys[:-1]))
        for config in CONFIGS_VALID if config.expected_output is not None
        for keys in flatten_keys(config.expected_output)
    ]
    @pytest.mark.parametrize("config,keys", CASES_RETURN_TYPES)
    def test_config_returned_types(self, config, keys):
        """
        Make sure each config-option is the right type.
        """
        expected_type = keys.pop(-1)
        value = config.create_config()

        # walk down the nested dict using the remaining keys
        for key in keys:
            value = value[key]

        if isinstance(expected_type, type):
            assert isinstance(value, expected_type), f"Expected type: {expected_type} but got {type(value)} for {keys} in {config.label}"
        else:
            # If the "expected_type" isn't a type, make sure it's that **exact** value then:
            assert value == expected_type, f"Expected value: {expected_type} but got {value} for {keys} in {config.label}"


    @pytest.mark.parametrize(
        "config",
        [config for config in CONFIGS_VALID if config.expected_output is not None],
        ids=lambda s: s.label
    )
    def test_no_extra_keys_exist_in_config(self, config):
        """
        Makes sure the config that is created, is exactly the same as
        `expected_output` config, i.e they're dicts with the same nested
        keys. (but possibly different values)
        """
        minimal_config = config.create_config()
        # If there's a key in minimal_config that's NOT in config.expected_output,
        # it won't get updated. The dict's won't then be equal.
        minimal_config_copy = copy.deepcopy(minimal_config)
        minimal_config_copy.update(config.expected_output)
        assert minimal_config_copy == config.expected_output, "Extra keys exist in `minimal_config`."
        # Same thing, but the other direction.
        tmp_expected_output = copy.deepcopy(config.expected_output)
        tmp_expected_output.update(minimal_config)
        assert tmp_expected_output == minimal_config, "Extra keys exist in `config.expected_output`."
