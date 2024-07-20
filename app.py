#!/usr/bin/env python3
import os

from aws_cdk import (
    Environment,
    App,
    Tags,
)

from ContainerManager.base_stack import ContainerManagerBaseStack
from ContainerManager.leaf_stack.main import ContainerManagerStack
from ContainerManager.leaf_stack.domain_stack import DomainStack
from ContainerManager.leaf_stack.link_together_stack import LinkTogetherStack
from ContainerManager.utils.config_loader import load_base_config, load_leaf_config

application_id = "ContainerManager"
application_id_tag_name = "ApplicationID"
app = App()
Tags.of(app).add(application_id_tag_name, application_id)

# Lets you reference self.account and self.region in your CDK code
# if you need to:
main_env = Environment(
    account=os.getenv('CDK_DEFAULT_ACCOUNT'),
    region=os.getenv('CDK_DEFAULT_REGION'),
)
us_east_1_env = Environment(
    account=main_env.account,
    region="us-east-1",
)

### These are also imported to the makefile, to guarantee things are consistent:
base_stack_name = f"{application_id}-BaseStack"
# def get_container_id(path: str) -> str:
#     "The container ID is the base filename, without any extension"
#     return os.path.basename(os.path.splitext(path)[0])


### Create the Base Stack for ALL applications:
base_config = load_base_config("./base-stack-config.yaml")
base_stack = ContainerManagerBaseStack(
    app,
    base_stack_name,
    description="The base VPC for all other ContainerManage stacks to use.",
    cross_region_references=True,
    env=main_env,
    config=base_config,
    application_id_tag_name=application_id_tag_name,
    application_id_tag_value=application_id,
)

### Create the application for ONE Container:
file_path = app.node.try_get_context("config-file")
if file_path:
    leaf_config = load_leaf_config(file_path)
    container_name_id = os.path.basename(os.path.splitext(file_path)[0])
    container_manager_id = f"ContainerManager-{container_name_id}"
    stack_tags = {
        "ContainerNameID": container_name_id,
        "ContainerManagerID": container_manager_id,
    }

    domain_stack = DomainStack(
        app,
        f"{container_manager_id}-DomainStack",
        description=f"Route53 for '{container_name_id}', since it MUST be in us-east-1",
        cross_region_references=True,
        env=us_east_1_env,
        container_name_id=container_name_id,
        base_stack=base_stack,
    )
    for key, val in stack_tags.items():
        Tags.of(domain_stack).add(key, val)

    manager_stack = ContainerManagerStack(
        app,
        f"{container_manager_id}-Stack",
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
    for key, val in stack_tags.items():
        Tags.of(manager_stack).add(key, val)

    link_together_stack = LinkTogetherStack(
        app,
        f"{container_manager_id}-LinkTogetherStack",
        description="To avoid a circular dependency, and connect the ContainerManagerStack and DomainStack together.",
        cross_region_references=True,
        env=us_east_1_env,
        domain_stack=domain_stack,
        manager_stack=manager_stack,
        container_name_id=container_name_id,
    )
    for key, val in stack_tags.items():
        Tags.of(link_together_stack).add(key, val)

app.synth()
