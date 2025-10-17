# Cloudformation Testing

This contains all the tests for the Cloudformation templates. Mainly verifying that whatever the config says, happens in the template(s).

We mainly do this by creating a [cdk template](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.assertions.Template.html), and using [Match](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.assertions.Match.html) to verify resources and properties.

## Structure

- `base_stack`: Everything for testing the shared-resources stack, that all other stacks depend on.
- `leaf_stack`: For testing the entire App. (A single leaf "stack" is technically multiple stacks combined to one.).

## Helpers in [conftest.py](./conftest.py)

- `to_template`: Takes a CDK Stack, and returns a CDK Template object for assertions. (You can't modify the stack or template after, so call this very last.).
- `print_template`: Prints the template and immediately exits to have the output instantly on your screen. Meant for developing / debugging tests.
- `cdk_app`: Returns a CdkApp class to initialize. `CdkApp(base_config=..., leaf_config=...)` You can use this to fine-tune the stack you're testing against, if the minimal_stack fixture isn't enough.
- `minimal_app`: Uses both minimal configs (base/leaf) to create a minimal app to test against.
