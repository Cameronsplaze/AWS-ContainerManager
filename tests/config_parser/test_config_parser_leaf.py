
import pytest

from tests.configs import (
    LEAF_VOLUMES,
    LEAF_CONTAINER_ENVIRONMENT,
)


class TestLeafConfigVolumes():
    # Loop on EACH volume config (there's only one Volume per config now):
    @pytest.mark.parametrize("config", LEAF_VOLUMES, ids=lambda s: s.label)
    def test_volume_properties(self, config):
        volume_input = config.config_input["Volume"]
        volume_output = config.create_config()["Volume"]
        # Both of these default to `maturity == Prod`, and `load_leaf_config` defaults to
        # Prod, so they're True here. Either way they ALWAYS exist in the returned volume_output:
        assert volume_input.get("KeepOnDelete", True) == volume_output["KeepOnDelete"]
        assert volume_input.get("EnableBackups", True) == volume_output["EnableBackups"]
        assert len(volume_input["Paths"]) == len(volume_output["Paths"]), "Volume path count mismatch."

        # Create a lookup for output paths by 'Path' to simplify checks
        output_paths_by_path = {p["Path"]: p for p in volume_output["Paths"]}

        # Check the paths for each volume:
        for input_path in volume_input["Paths"]:
            assert "Path" in input_path, "Each volume path must have a 'Path' key."
            # Get the corresponding output path:
            assert input_path["Path"] in output_paths_by_path, f"Volume path {input_path['Path']} not found in output."
            output_path = output_paths_by_path[input_path["Path"]]

            # ReadOnly should default to False, AND always exist in the returned path:
            assert input_path.get("ReadOnly", False) == output_path["ReadOnly"], f"Volume path {input_path['Path']} ReadOnly mismatch."



class TestLeafConfigEnvironment():
    # Loop on EACH environment variable:
    @pytest.mark.parametrize(
        "input_name,input_value",
        LEAF_CONTAINER_ENVIRONMENT.config_input["Container"]["Environment"].items(),
    )
    def test_casting_variables(self, input_name, input_value):
        config = LEAF_CONTAINER_ENVIRONMENT.create_config()
        env = config["Container"]["Environment"]
        assert input_name in env, f"Missing environment variable {input_name}."
        output_value = env[input_name]
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
