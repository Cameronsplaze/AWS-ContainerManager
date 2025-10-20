
import os

def pytest_configure(config): # pylint: disable=unused-argument
    """ Runs at the very start of pytest execution. """

    # Make sure AWS is faked, so it's impossible to make real AWS calls during tests:
    assert os.getenv("AWS_ACCESS_KEY_ID") == "fake_access_key"
    assert os.getenv("AWS_SECRET_ACCESS_KEY") == "fake_secret_key"
    shared_file = os.getenv("AWS_SHARED_CREDENTIALS_FILE")
    assert shared_file is not None
    assert os.path.isfile(shared_file)
