# Lambda Functions Testing

We use [aws_moto](https://docs.getmoto.org/en/latest/docs/getting_started.html) to mock AWS services, and verify [the lambdas](../../ContainerManager/leaf_stack_group/lambda_functions/) work as expected. It lets you use [boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html) to create virtual AWS resources locally, as if they were in the cloud. It also mocks the existing boto3 client calls in lambda, so everything is verified.
