
"""
A helper script that lets you use CfnParams, but also use their values in a
pythonic-way without trying to modify tokens.
"""

import os

from typing import Union

from aws_cdk import (
    Stack,
    CfnParameter,
)

def save_param(stack: Stack, key: str, val: Union[str, int, float, bool], description: str="") -> None:
    """
    Set a CfnParameter Easily. Just used to save input args mainly.
    """
    # Let param_type be dynamic, we're not in CFN Yaml anymore.
    try:
        float(val)
        param_type = "Number"
    except ValueError:
        param_type = "String"

    ## This is to see what the stack was deployed with in the cfn parameters tab:
    # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.CfnParameter.html
    return CfnParameter(
        stack,
        key,
        type=param_type,
        default=val,
        description=f"{description}{' ' if description else ''}(Don't Edit in CloudFormation Console)",
        # Since changing it in the console (if you use get_param) won't do anything, don't let them:
        allowed_values=[val],
    )

def get_param(
        stack: Stack,
        key: str,
        # Passing in 'None' here is possible. It means 'Don't create the
        #  things referencing this'. Need ... to know if they SET None.
        default: Union[str, int, float, bool, None]=...,
        description: str="",
    ) -> Union[str, int, float, bool]:
    """
    Get a parameter from the environment, or use the default if it's not set.

    Used to configure stacks at deploy time. Returns what the parameter is set to, instead
    of a token, so you can call things like `arg.lower()` on the return value.

        Stack: The stack to add the parameter to
        key: The name of the parameter to grab from env vars
        default: The default value if not set. DON'T set this if you want it to be required.
        description: The description to attach to the param in AWS
    """
    # If val is in the environment, just use that:
    val = os.environ.get(key)
    # Else check if a default is declared:
    if val is None:
        if default is ...:
            raise ValueError(f"Missing required parameter: '{key}', and no default is set.")
        val = default
    # val could be a string of int, because of os.environ.get anyways,
    # and CfnParameter only accepts strings. Keep it as a string here
    val = str(val)

    ## Create the parameter:
    parameter = save_param(stack, key, val, description)

    ## If you're expecting a number, change it away from a string:
    #   (CfnParameter *wants* the input as a string, but nothing else does)
    if parameter.type == "Number":
        val = float(val) if "." in val else int(val)
    ## If it's a bool, change it to one:
    elif val.lower() in ["true", "false"]:
        val = val.lower() == "true"
    ## If it's 'None', change it to one:
    elif val == "None":
        val = None
    return val
