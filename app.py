#!/usr/bin/env python3
import os

import aws_cdk as cdk

from ContainerManager_VPC.vpc_base_stack import VpcBaseStack
from ContainerManager.container_manager_stack import ContainerManagerStack



app = cdk.App()

# Lets you reference self.account and self.region in your CDK code
# if you need to:
env = cdk.Environment(
    account=os.getenv('CDK_DEFAULT_ACCOUNT'),
    region=os.getenv('CDK_DEFAULT_REGION')
)

# Create the VPC for ALL stacks:
vpc_stack = VpcBaseStack(
    app,
    "ContainerManager-VPC",
    description="The base VPC for all other ContainerManage stacks to use.",
    env=env,
)

# Create the stack:
ContainerManagerStack(
    app,
    "ContainerManagerStack",
    description="For automatically managing a single container.",
    env=env,
    vpc=vpc_stack.vpc,
    sg_vpc_traffic=vpc_stack.sg_vpc_traffic,
)

app.synth()
