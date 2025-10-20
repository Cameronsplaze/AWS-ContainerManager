
import pytest

@pytest.fixture()
def setup_env(monkeypatch):
    def _set_envs(env_vars: dict):
        """ Set the default env vars for the lambda """
        for k, v in env_vars.items():
            monkeypatch.setenv(k, v)
    return _set_envs
