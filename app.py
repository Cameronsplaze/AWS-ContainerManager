#!/usr/bin/env python3
import os

import aws_cdk as cdk

from GameManager.vpc_base_stack import VpcBaseStack
from GameManager.game_manager_stack import GameManagerStack



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
    "GameManager-VPC",
    description="The base VPC for all other stacks to use.",
    env=env,
)

# Create the stack:
GameManagerStack(
    app,
    "GameManagerStack",
    description="For automatically managing a single game server (for now).",
    env=env,
    vpc=vpc_stack.vpc,
    sg_ecs_traffic=vpc_stack.sg_ecs_traffic,
)

app.synth()
