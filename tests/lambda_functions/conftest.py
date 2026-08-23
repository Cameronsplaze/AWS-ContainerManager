
from dataclasses import dataclass

import pytest


@dataclass
class LambdaContext:
    """ Stand-in for the context object the Lambda runtime supplies. """
    function_name: str = "test-function"
    memory_limit_in_mb: int = 128
    invoked_function_arn: str = "arn:aws:lambda:us-west-2:123456789012:function:test-function"
    aws_request_id: str = "00000000-0000-0000-0000-000000000000"

@pytest.fixture()
def lambda_context():
    return LambdaContext()

@pytest.fixture()
def setup_env(monkeypatch):
    def _set_envs(env_vars: dict):
        """ Set the default env vars for the lambda """
        for k, v in env_vars.items():
            monkeypatch.setenv(k, v)
    return _set_envs
