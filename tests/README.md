# Running Tests

<!--
NOTE TO SELF: This is what protects your Minecraft server. Make it count. 
-->

The core framework uses [pytest](https://docs.pytest.org/en/stable/), including helper plugins like [pytest-cov](https://coverage.readthedocs.io/en/latest/index.html). Each section contains a README.md, with more info on that section:

- [config_parser](./config_parser/) is to test the config loading, and schema. It's to make sure values are also casted correctly, and defaults are applied.
- [cloudformation](./cloudformation/) is to test the CDK stacks, and the synthed templates. It's to make sure the templates have the correct resources and properties.
- [lambda_functions](./lambda_functions/) is the lambda functions themselves. Only `spin_down_asg_on_error` is done so far, since it was the simplest. The other two should be done soon.

Since both `config_parser` and `cloudformation` use the same config objects, in [configs.py](./configs.py). We use [config_parser](./config_parser/) to verify loading the config gives the expected yaml. [cloudformation](./cloudformation/) is to verify the CDK stacks are synthesized correctly, given the expected yaml. [configs.py](./configs.py) lets us test both sides without duplicating effort.

TODO:

- Look into updating the actions. More details in [#147](https://github.com/Cameronsplaze/AWS-ContainerManager/issues/147).
  - Which will also include updating that section's README, and updating the "Required Actions" list.
