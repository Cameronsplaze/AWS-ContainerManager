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
app = App()

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


# Create the Base Stack for ALL applications:
base_config = load_base_config("./base-stack-config.yaml")
application_id = "ContainerManager"
application_id_tag_name = "ApplicationID"
Tags.of(app).add(application_id_tag_name, application_id)
base_stack = ContainerManagerBaseStack(
    app,
    # NOTE: IF THIS NAME EVER CHANGES, also update the 'base_stack_name' var in the Makefile.
    f"{application_id}-BaseStack",
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
    # Get the filename, without the extension:
    container_name_id = os.path.basename(os.path.splitext(file_path)[0])
    container_manager_id = f"ContainerManager-{container_name_id}"
    application_id_tag_name = "ContainerManagerID"

    domain_stack = DomainStack(
        app,
        f"{container_manager_id}-DomainStack",
        description=f"Route53 for '{container_name_id}', since it MUST be in us-east-1",
        cross_region_references=True,
        env=us_east_1_env,
        container_name_id=container_name_id,
        base_stack=base_stack,
    )
    Tags.of(domain_stack).add(application_id_tag_name, container_manager_id)

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
    Tags.of(manager_stack).add(application_id_tag_name, container_manager_id)

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
    Tags.of(link_together_stack).add(application_id_tag_name, container_manager_id)

app.synth()
