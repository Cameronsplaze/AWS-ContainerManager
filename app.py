#!/usr/bin/env python3

"""
CDK Application for managing containers in AWS
"""

import os

from aws_cdk import (
    # Aspects,
    App,
    Environment,
    Tags,
)
# import cdk_nag

from ContainerManager.base_stack import BaseStack
from ContainerManager.leaf_stack_group.domain_stack import DomainStack
from ContainerManager.leaf_stack_group.container_manager_stack import ContainerManagerStack
from ContainerManager.leaf_stack_group.start_system_stack import StartSystemStack
from ContainerManager.utils import load_base_config, load_leaf_config


# https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.App.html
app = App()
application_id = app.node.get_context("_application_id")
APPLICATION_ID_TAG_NAME = "ApplicationId"
### TODO: Finish going through all the cdk_nag checks:
# Aspects.of(app).add(cdk_nag.AwsSolutionsChecks(verbose=True))
Tags.of(app).add(APPLICATION_ID_TAG_NAME, application_id)

### Fact-check the maturity, and save it for leaf stacks:
# (Makefile defaults to prod if not set. We want to fail-fast
# here, so throw if it doesn't exist)
maturity = app.node.get_context("maturity")
supported_maturities = ["devel", "prod"]
assert maturity in supported_maturities, f"ERROR: Unknown maturity. Must be in {supported_maturities}"


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

##################
### Base Stack ###
##################
base_config = load_base_config("./base-stack-config.yaml")
### Create the Base Stack VPC for ALL leaf stacks:
base_stack = BaseStack(
    app,
    f"{app.node.get_context('_base_stack_name')}",
    description="The base VPC for all other ContainerManage stacks to use.",
    cross_region_references=True,
    env=main_env,
    config=base_config,
    application_id_tag_name=APPLICATION_ID_TAG_NAME,
    application_id_tag_value=application_id,
)

##################
### Leaf Stack ###
##################
### Create the application for ONE Container:
file_path = app.node.try_get_context("config-file")
if file_path:
    leaf_config = load_leaf_config(file_path, maturity=maturity)
    # You can override container_id if you need to:
    container_id = app.node.try_get_context("container-id")
    if not container_id:
        container_id = os.path.basename(os.path.splitext(file_path)[0])
    container_id = container_id.lower()
    # For stack names, turn "minecraft.java.example" into "MinecraftJavaExample":
    container_id_alpha = "".join(e for e in container_id.title() if e.isalnum())

    stack_tags = {
        "ContainerId": container_id,
        "StackId": f"{application_id}-{container_id_alpha}",
    }

    ### Create the Base Stack Domain for ALL leaf stacks:
    domain_stack = DomainStack(
        app,
        f"{application_id}-{container_id_alpha}-Domain",
        description=f"The HostedZone for '{container_id}'.",
        cross_region_references=True,
        env=us_east_1_env,
        container_id=container_id,
        base_stack=base_stack,
    )
    for key, val in stack_tags.items():
        Tags.of(domain_stack).add(key, val)


    container_manager_stack = ContainerManagerStack(
        app,
        f"{application_id}-{container_id_alpha}-ContainerManager",
        description="For managing, and automatically spinning DOWN the container.",
        cross_region_references=True,
        env=main_env,
        base_stack=base_stack,
        domain_stack=domain_stack,
        application_id=application_id,
        container_id=container_id,
        config=leaf_config,
    )
    for key, val in stack_tags.items():
        Tags.of(container_manager_stack).add(key, val)


    start_system_stack = StartSystemStack(
        app,
        f"{application_id}-{container_id_alpha}-StartSystem",
        description="Everything for spinning UP the container when someone connects.",
        cross_region_references=True,
        env=us_east_1_env,
        domain_stack=domain_stack,
        container_manager_stack=container_manager_stack,
        container_id=container_id,
    )
    for key, val in stack_tags.items():
        Tags.of(start_system_stack).add(key, val)

app.synth()
