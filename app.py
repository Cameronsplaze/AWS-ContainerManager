#!/usr/bin/env python3
import os

import aws_cdk as cdk

from ContainerManager.base_stack import ContainerManagerBaseStack
from ContainerManager.leaf_stack.main import ContainerManagerStack
from ContainerManager.leaf_stack.domain_info import DomainStack
from ContainerManager.leaf_stack.link_together import LinkTogetherStack
from ContainerManager.utils.config_loader import load_config
app = cdk.App()

# Lets you reference self.account and self.region in your CDK code
# if you need to:
main_env = cdk.Environment(
    account=os.getenv('CDK_DEFAULT_ACCOUNT'),
    region=os.getenv('CDK_DEFAULT_REGION'),
)
us_east_1_env = cdk.Environment(
    account=main_env.account,
    region="us-east-1",
)


# Create the base VPC for ALL stacks:
base_config = load_config("./base-stack-config.yaml")
base_stack = ContainerManagerBaseStack(
    app,
    "ContainerManager-BaseStack",
    description="The base VPC for all other ContainerManage stacks to use.",
    cross_region_references=True,
    env=main_env,
    config=base_config,
)

### Create the stack for ONE Container:
file_path = app.node.try_get_context("config-file")
if file_path:
    leaf_config = load_config(file_path)
    # Get the filename, without the extension:
    container_name_id = os.path.basename(os.path.splitext(file_path)[0])

    domain_stack = DomainStack(
        app,
        f"ContainerManager-{container_name_id}-DomainStack",
        description=f"Route53 for '{container_name_id}', since it MUST be in us-east-1",
        cross_region_references=True,
        env=us_east_1_env,
        container_name_id=container_name_id,
        base_stack=base_stack,
    )

    manager_stack = ContainerManagerStack(
        app,
        f"ContainerManager-{container_name_id}-Stack",
        description="For automatically managing a single container.",
        # cross_region_references lets this stack reference the domain_stacks
        # variables, since that one is ONLY in us-east-1
        cross_region_references=True,
        env=main_env,
        base_stack=base_stack,
        domain_stack=domain_stack,
        container_name_id=container_name_id,
        config=leaf_config,
    )
    LinkTogetherStack(
        app,
        f"ContainerManager-{container_name_id}-LinkTogetherStack",
        description="To avoid a circular dependency, and connect the ContainerManagerStack and DomainStack together.",
        cross_region_references=True,
        env=us_east_1_env,
        domain_stack=domain_stack,
        manager_stack=manager_stack,
    )

app.synth()
