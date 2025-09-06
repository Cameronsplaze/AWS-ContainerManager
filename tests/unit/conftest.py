
import pytest

import aws_cdk as cdk
from aws_cdk.assertions import Template

from ContainerManager.base_stack import BaseStack
from ContainerManager.leaf_stack_group.domain_stack import DomainStack
from ContainerManager.leaf_stack_group.container_manager_stack import ContainerManagerStack

@pytest.fixture(scope="class")
def cdk_app():
    return cdk.App()

################
## BASE STACK ##
################
@pytest.fixture(scope="class")
def create_base_stack(cdk_app):
    def _create_base_stack(config) -> tuple[Template, BaseStack]:
        base_stack = BaseStack(
            cdk_app,
            "TestBaseStack",
            config=config,
            application_id_tag_name="ApplicationId",
            application_id_tag_value="test-app"
        )
        base_template = Template.from_stack(base_stack)
        return base_template, base_stack
    return _create_base_stack


#########################
## LEAF STACK - Domain ##
#########################
@pytest.fixture(scope="class")
def create_leaf_stack_domain(cdk_app):
    def _create_domain_stack(base_stack) -> tuple[Template, DomainStack]:
        domain_stack = DomainStack(
            cdk_app,
            "TestLeafStack-Domain",
            container_id="test-stack",
            base_stack=base_stack,
        )
        domain_template = Template.from_stack(domain_stack)
        return domain_template, domain_stack
    return _create_domain_stack


# ###################################
# ## LEAF STACK - ContainerManager ##
# ###################################
# @pytest.fixture(scope="class")
# def leaf_stack_container_manager(cdk_app, base_stack, leaf_stack_domain):
#     return ContainerManagerStack(
#         cdk_app,
#         "TestLeafStack-ContainerManager",
#         base_stack=base_stack,
#         domain_stack=leaf_stack_domain,
#         application_id="test-app",
#         container_id="test-stack",
#         config={
#             "Ec2": {
#                 "InstanceType": "t3.micro",
#                 # TODO: Make this disappear when converting to a fixture:
#                 "MemoryInfo": {
#                     "SizeInMiB": 1024,
#                 },
#             },
#             "Container": {
#                 "Image": "hello-world:latest",
#                 "Ports": [],
#                 "Environment": {},
#             },
#             "Volumes": [],
#             "Watchdog": {
#                 "Threshold": 2000,
#                 "MinutesWithoutConnections": 7
#             },
#             "AlertSubscription": {},
#         },
#     )

# @pytest.fixture(scope="class")
# def leaf_template_container_manager(leaf_stack_container_manager):
#     return Template.from_stack(leaf_stack_container_manager)
