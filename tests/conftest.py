
import os

def pytest_configure(config): # pylint: disable=unused-argument
    """ Runs at the very start of pytest execution. """

    # Make sure AWS is faked, so it's impossible to make real AWS calls during tests:
    assert os.getenv("AWS_ACCESS_KEY_ID") == "fake_access_key"
    assert os.getenv("AWS_SECRET_ACCESS_KEY") == "fake_secret_key"
    assert os.getenv("AWS_SHARED_CREDENTIALS_FILE") is not None, "We don't want your REAL aws config!"
    aws_creds_file = os.getenv("AWS_SHARED_CREDENTIALS_FILE")
    assert aws_creds_file is not None
    assert not os.path.isfile(aws_creds_file), "Don't have a real creds file, AWS calls should be mocked anyways."
