#!/usr/bin/env python3
import os

from aws_cdk import (
    # Aspects,
    App,
    Environment,
    Tags,
)
import cdk_nag

from ContainerManager.base_stack import ContainerManagerBaseStack
from ContainerManager.leaf_stack.main import ContainerManagerStack
from ContainerManager.leaf_stack.domain_stack import DomainStack
from ContainerManager.leaf_stack.link_together_stack import LinkTogetherStack
from ContainerManager.utils.config_loader import load_base_config, load_leaf_config


application_id = "ContainerManager"
application_id_tag_name = "ApplicationId"
# https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.App.html
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
    container_id = os.path.basename(os.path.splitext(file_path)[0])
    stack_tags = {
        "ContainerId": container_id,
    }

    domain_stack = DomainStack(
        app,
        f"{application_id}-{container_id}-DomainStack",
        description=f"Route53 for '{container_id}', since it MUST be in us-east-1",
        cross_region_references=True,
        env=us_east_1_env,
        container_id=container_id,
        base_stack=base_stack,
    )
    for key, val in stack_tags.items():
        Tags.of(domain_stack).add(key, val)

    manager_stack = ContainerManagerStack(
        app,
        f"{application_id}-{container_id}-Stack",
        description="For automatically managing a single container.",
        # cross_region_references lets this stack reference the domain_stacks
        # variables, since that one is ONLY in us-east-1
        cross_region_references=True,
        env=main_env,
        base_stack=base_stack,
        domain_stack=domain_stack,
        container_id=container_id,
        config=leaf_config,
    )
    for key, val in stack_tags.items():
        Tags.of(manager_stack).add(key, val)

    link_together_stack = LinkTogetherStack(
        app,
        f"{application_id}-{container_id}-LinkTogetherStack",
        description=f"To avoid a circular dependency, and connect '{manager_stack.stack_name}' and '{domain_stack.stack_name}' together.",
        cross_region_references=True,
        env=us_east_1_env,
        domain_stack=domain_stack,
        manager_stack=manager_stack,
        container_id=container_id,
    )
    for key, val in stack_tags.items():
        Tags.of(link_together_stack).add(key, val)

app.synth()
# Aspects.of(app).add(cdk_nag.AwsSolutionsChecks(verbose=True))
# Aspects.of(app).add(cdk_nag.HIPAASecurityChecks(verbose=True))
