import os

from typing import Union

from aws_cdk import (
    Stack,
    CfnParameter,
)


def get_param(stack: Stack, key: str, default: Union[str, int, float]=None, param_type: str="String", description: str="") -> str:
    """
    Get a parameter from the environment, or use the default if it's not set.

        Stack: The stack to add the parameter to
        key: The name of the parameter to grab from env vars
        default: The default value if not set. DON'T set this if you want it to be required.
        param_type: The AWS parameter type to create ("String", "Number"...)
        description: The description to attach to the param in AWS
    """
    val = os.environ.get(key) or default
    if val is None:
        raise ValueError(f"Missing required parameter: '{key}', and no default is set.")
    val = str(val)

    # This is to see what the stack was deployed with in the cfn parameters tab:
    CfnParameter(
        stack,
        key,
        type=param_type,
        default=val,
        # Since changing it in the console won't do anything anyways, don't let them:
        allowed_values=[val],
        description=f"{description}{' ' if description else ''}(Redeploy pipeline to change)"
    )

    # If you're expecting a number, change it away from a string:
    #   (CfnParameter *wants* the input as a string, but nothing else does)
    if param_type == "Number":
        val = float(val) if "." in val else int(val)
    return val
