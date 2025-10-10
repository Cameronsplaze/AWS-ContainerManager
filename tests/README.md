# Running Tests

<!--
NOTE TO SELF: This is what protects your Minecraft server. Make it count. 
-->

The core framework will use [pytest](https://docs.pytest.org/en/stable/), including helper plugins like [pytest-cov](https://coverage.readthedocs.io/en/latest/index.html).

## Testing Against CDK Itself

[CDK has three main ways](https://docs.aws.amazon.com/cdk/v2/guide/testing.html) to test your code. Using SAM for lambda, using unit testing for making sure the synthed template has specific features (i.e lambda functions can only have specific runtimes), and snapshot testing.

### Testing with SAM

I'm not sure we need this yet. It's more so for running the lambda functions locally.

- [Installing SAM](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html#install-sam-cli-instructions)
- [Local testing AWS CDK applications with AWS SAM](https://docs.aws.amazon.com/cdk/v2/guide/testing-locally-with-sam-cli.html)
- [Getting started with locally testing](https://docs.aws.amazon.com/cdk/v2/guide/testing-locally-getting-started.html)

With SAM you can do something like:

```bash
sam local invoke <FUNCTION_NAME> --event ./tests/events/hello-world.json -t ./cdk.out/<StackName>-<DeployPrefix>.template.json
# For example something like:
sam local invoke HelloWorldLambdaFunctionDA383F07 --event ./tests/events/hello-world.json -t ./cdk.out/ContainerManager.template.json
```

### Unit Testing

There's a few main areas we can unit test, each will have a different focus and tools to import.

- Testing Synthed Templates: You can do things like make sure the lambda function runtime matches the powertools runtime it uses, or make a minimum python version.
- Testing [Lambda Function](../ContainerManager/leaf_stack_group/lambda/) Contents: When importing the lambda python scripts to test, a good package for mocking AWS services is [moto](https://docs.getmoto.org/en/latest/). It'll stop us from *actually* calling AWS services, and setup a virtual vision of them that we can use to test against (including adding entries to a DB).
- Testing the [Config Loader](../ContainerManager/utils/config_loader.py): Make sure we're loading the yaml's correctly, and make sure it catches incorrect types too. Try to remember all the corner-cases hit when writing it.
- Mayyybe test for timing? See which parts take the longest to spin up, and also make sure we never go backwards.

### Snapshot Testing

Snapshot testing is just saving a synthed template, and erroring if that template changes. It's useful if you have a stable project and you're about to refactor, but NOT when you're in the development phase.

## This Project's Tests

Don't judge the directory structure yet, I'm rapidly iterating on tests. The main focus is first to ensure we can load configs correctly. After that, we can use the same configs to create synthed templates to test against.

- `config_parser` is to test the config loading, and schema. It's to make sure values are also casted correctly, and defaults are applied.
- `cloudformation` is to test the CDK stacks, and the synthed templates. It's to make sure the templates have the correct resources, and that the resources have the correct properties.
- Still need to add a directory for testing the lambda functions themselves.

Since both `config_parser` and `cloudformation` use the same config objects, the objects should probably me moved here into the testing root. (But that's directory structure, saving it for last.). Same with everything being inside the `test_base_config_parser.py` file, that WILL be split up later.

TODO:

- Split up and re-organize the different "CONFIG" objects. Think about bringing them to this tests root directory, since both config_parser and cloudformation use them.
- Organize and break apart `test_base_config_parser.py`
- Rewrite this README.md, and maybe sprinkle more throughout this part of the repo as needed.
  - Add fixture helpers too for writing tests, like `print_template`
- Go back through commits/PR's, and look for bugs that have been fixed but not tested against.
- Look into updating the actions. More details in [#147](https://github.com/Cameronsplaze/AWS-ContainerManager/issues/147).
  - Which will also include updating that section's README, and updating the "Required Actions" list.
- Enforce in-transit encryption for EFS.
