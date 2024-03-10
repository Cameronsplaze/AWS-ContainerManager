#!/usr/bin/env python3
import os

import aws_cdk as cdk

from ContainerManager.base_stack import ContainerManagerBaseStack
from ContainerManager.container_manager_stack import ContainerManagerStack



app = cdk.App()

# Lets you reference self.account and self.region in your CDK code
# if you need to:
env = cdk.Environment(
    account=os.getenv('CDK_DEFAULT_ACCOUNT'),
    region=os.getenv('CDK_DEFAULT_REGION')
)

# Create the VPC for ALL stacks:
base_stack = ContainerManagerBaseStack(
    app,
    "ContainerManager-BaseStack",
    description="The base VPC for all other ContainerManage stacks to use.",
    env=env,
)

# Create the stack:
container_name_id = os.environ.get('CONTAINER_NAME_ID') or 'UKN'
ContainerManagerStack(
    app,
    # TODO: Have good value here. Maybe same as DNS CNAME?
    f"ContainerManager-{container_name_id}-Stack",
    description="For automatically managing a single container.",
    env=env,
    base_stack=base_stack,
    container_name_id=container_name_id,
)

app.synth()
