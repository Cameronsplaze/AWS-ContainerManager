
"""
Base Class for all Lambda Functions in the leaf_stack_group.
"""

from typing import cast

from aws_cdk import (
    Stack,
    aws_lambda,
)
from constructs import Construct

from ContainerManager.utils import Maturity


class PowertoolsFunction(aws_lambda.Function):
    """
    A lambda function with the Powertools layer and env vars already wired up.

    - `handler` and `runtime`: Every lambda uses the same, CAN'T override. 
    - `layers` and `environment` are MERGED with the defaults below, overridable.
    """

    ## Bump this to move EVERY lambda in the project to a new python version:
    RUNTIME = aws_lambda.Runtime.PYTHON_3_14
    # Must match the ec2 instance's arch, or the layer won't load:
    ARCHITECTURE = "x86_64"
    # Every lambda_functions/*/main.py uses this same entrypoint:
    HANDLER = "main.lambda_handler"

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        code: aws_lambda.Code,
        layers: list[aws_lambda.ILayerVersion] | None=None,
        environment: dict[str, str] | None=None,
        **kwargs,
    ) -> None:
        super().__init__(
            scope,
            construct_id,
            code=code,
            handler=self.HANDLER,
            runtime=self.RUNTIME,
            ## Both of these are DEFAULTS. Anything the caller declares wins:
            layers=[self._get_powertools_layer(scope), *(layers or [])],
            environment={**self._get_powertools_env_vars(scope), **(environment or {})},
            **kwargs,
        )

    @classmethod
    def _get_powertools_layer(cls, scope: Construct) -> aws_lambda.ILayerVersion:
        """ Import the Powertools layer. """
        ## Only one powertools layer per stack is needed:
        stack = Stack.of(scope)
        layer_id = "LambdaPowertoolsLayer"
        existing_layer = stack.node.try_find_child(layer_id)
        if existing_layer:
            # `try_find_child` only promises an IConstruct back, but we know it's a layer:
            return cast(aws_lambda.ILayerVersion, existing_layer)

        ## Let AWS tell us the latest layer arn, instead of hard-coding the version:
        # https://docs.aws.amazon.com/powertools/python/latest/getting-started/install/#using-ssm-parameter-store
        layer_arn = f"{{{{resolve:ssm:/aws/service/powertools/python/{cls.ARCHITECTURE}/{cls.RUNTIME.name}/latest}}}}"  # pylint: disable=no-member
        return aws_lambda.LayerVersion.from_layer_version_arn(
            stack,
            layer_id,
            layer_version_arn=layer_arn,
        )

    @classmethod
    def _get_powertools_env_vars(cls, scope: Construct) -> dict[str, str]:
        """ The env vars Powertools itself reads, to configure the logger. """
        ## app.py has safeguards on maturity. And we WANT to fail if something is misconfigured:
        maturity = Maturity(scope.node.get_context("maturity"))

        ### Switch the possible stack Id's, down to the same value
        # Devel has an extra segment than Prod, keep one extra:
        segment = 2 if maturity == Maturity.PROD else 3
        # ContainerManager-ExampleContainer/NestedStackId -> ContainerManager-ExampleContainer
        id_prefix = scope.to_string().split("/")[0]
        # ContainerManager-ExampleContainer-StartSystem -> ContainerManager-ExampleContainer
        stack_id = "-".join(id_prefix.split("-")[:segment])
        # https://docs.aws.amazon.com/powertools/python/latest/core/logger/#environment-variables
        return {
            "POWERTOOLS_SERVICE_NAME":stack_id,
            "POWERTOOLS_LOG_LEVEL": "INFO" if maturity == Maturity.PROD else "DEBUG",
        }
