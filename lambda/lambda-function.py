import boto3
import os

required_vars = ["AWS_REGION"]
missing_vars = [x for x in required_vars if not os.environ.get(x)]
if any(missing_vars):
    raise RuntimeError(f"Missing environment vars: {' '.join(missing_vars)}")

def lambda_handler(event, context):
    # This lambda is apart of a stack, so ecs will always be in
    # the same region as this function:
    ecs_clent = boto3.client('ecs', region_name=os.environ['AWS_REGION'])
