#!/usr/bin/env python3
import os

import aws_cdk as cdk

from ContainerManager_Base.base_stack import ContainerManagerBaseStack
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
ContainerManagerStack(
    app,
    # TODO: Have good value here. Maybe same as DNS CNAME?
    f"ContainerManager-{os.environ.get('GAME_NAME') or 'Unknown'}-Stack",
    description="For automatically managing a single container.",
    env=env,
    vpc=base_stack.vpc,
    sg_vpc_traffic=base_stack.sg_vpc_traffic,
)

app.synth()
