import tempfile

import pytest

_aws_credentials = """
[default]
aws_access_key_id = fake_access_key
aws_secret_access_key = fake_secret_key
"""

@pytest.fixture()
def setup_env(monkeypatch):
    def _set_envs(env_vars: dict):
        """ Set the default env vars for the lambda """
        for k, v in env_vars.items():
            monkeypatch.setenv(k, v)
    return _set_envs

# Can't use scope, or you'll get a scope-mismatch.
@pytest.fixture(autouse=True)
def block_aws_calls(monkeypatch):
    """
    Fixture to block REAL AWS calls during tests.
    Moto will still work, but REAL boto3 calls will fail.
    """
    # https://docs.getmoto.org/en/latest/docs/getting_started.html#how-do-i-avoid-tests-from-mutating-my-real-infrastructure
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "fake_access_key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "fake_secret_key")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "fake_session_token")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "fake_security_token")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-west-2")
    # https://stackoverflow.com/a/65017491/11650472
    with tempfile.NamedTemporaryFile("w+", suffix=".yaml", delete=True) as tmp:
        tmp.write(_aws_credentials)
        tmp.flush()
        monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", tmp.name)
        yield
