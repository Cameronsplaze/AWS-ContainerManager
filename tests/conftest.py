
import os

def pytest_configure(config): # pylint: disable=unused-argument
    """ Runs at the very start of pytest execution. """

    # Make sure AWS is faked, so it's impossible to make real AWS calls during tests:
    assert os.getenv("AWS_ACCESS_KEY_ID") == "fake_access_key"
    assert os.getenv("AWS_SECRET_ACCESS_KEY") == "fake_secret_key"
    assert os.path.abspath(os.getenv("AWS_SHARED_CREDENTIALS_FILE")) == os.path.abspath("./tests/fake_aws_credentials")
