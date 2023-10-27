#!/usr/bin/env python3
import os

import aws_cdk as cdk

# from GameManager_private.game_manager_stack import GameManagerStack
from GameManager_public.game_manager_stack import GameManagerStack

app = cdk.App()

# Lets you reference self.account and self.region in your CDK code
# if you need to:
env = cdk.Environment(
    account=os.getenv('CDK_DEFAULT_ACCOUNT'),
    region=os.getenv('CDK_DEFAULT_REGION')
)

# Create the stack:
GameManagerStack(
    app,
    "GameManagerStack-v3",
    description="For automatically managing a single game server (for now).",
    env=env,
)

app.synth()
