# Running Tests

<!--
NOTE TO SELF: This is what protects your Minecraft server. Make it count. 
-->

The core framework uses [pytest](https://docs.pytest.org/en/stable/), including helper plugins like [pytest-cov](https://coverage.readthedocs.io/en/latest/index.html). Each section contains a README.md, with more info on that section:

- [config_parser](./config_parser/README.md) is to test the config loading, and schema. It's to make sure values are also casted correctly, and defaults are applied.
- [cloudformation](./cloudformation/README.md) is to test the CDK stacks, and the synthed templates. It's to make sure the templates have the correct resources and properties.
- [lambda_functions](./lambda_functions/README.md) is the lambda functions themselves. Only `spin_down_asg_on_error` is done so far, since it was the simplest. The other two should be done soon.

Since both `config_parser` and `cloudformation` use the same config objects, in [configs.py](./configs.py). We use [config_parser](./config_parser/) to verify loading the config gives the expected yaml. [cloudformation](./cloudformation/) is to verify the CDK stacks are synthesized correctly, given the expected yaml. [configs.py](./configs.py) lets us test both sides without duplicating effort.

We run pytest through [tox](https://tox.wiki/en/), so we can create the environment to test in. Mainly, remove the AWS creds/configuration while the test suite is running. This makes sure we don't accidentally hit AWS directly, if we miss a mock somewhere.

- First I tried monkeypatching the env-vars in a session-level fixture. The problem is this only mocks boto3 clients created AFTER tests are collected. If there are any boto3 clients created at import-time, or if you use boto3 calls in `pytest.mark.parametrize`, those calls will still use the REAL creds. I want to guarantee if the suite is running, you NEVER hit AWS directly.
- The other option was to use `os.environ` in `pytest_configure`, but the problem is I don't want to nuke the developers REAL creds after the tests are over. `tox` was the only option I saw that restores env-vars after the tests are done.
- With the current option, we can verify the test can ONLY run through `tox` with the asserts I have in [pytest_configure(config)](./conftest.py). If the env-vars aren't faked, that'll stop the suite from even collecting the tests.
