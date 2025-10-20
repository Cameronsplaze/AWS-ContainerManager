# Lambda Functions Testing

We use [aws_moto](https://docs.getmoto.org/en/latest/docs/getting_started.html) to mock AWS services, and verify [the lambdas](../../ContainerManager/leaf_stack_group/lambda_functions/) work as expected. It lets you use [boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html) to create virtual AWS resources locally, as if they were in the cloud. It also mocks the existing boto3 client calls in lambda, so everything is verified.

## Notes on Writing Tests (FAQ's)

### Why no boto-creation in setup_class?

`setup_class` is too soon, so the clients won't be mocked. By doing them in `setup_method` instead, it makes sure they're mocked, AND each test has a fresh environment to test in.

### Why are all the boto3 clients in the repo wrapped in @cache?

If they're initialized on import, pytest won't have a chance to mock them before they're created. AND if they're not used, they're very expensive to create anyways. There's no downside to not doing it this way.
