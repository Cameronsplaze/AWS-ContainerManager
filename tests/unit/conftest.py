
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
def base_stack(cdk_app):
    return BaseStack(
        cdk_app,
        "TestBaseStack",
        config={
            "Vpc": {
                "MaxAZs": 1,
            },
            "AlertSubscription": {},
            "Domain": {
                "Name": "example.com",
                "HostedZoneId": "Z123456ABCDEFG",
            },
        },
        application_id_tag_name="ApplicationId",
        application_id_tag_value="test-app"
    )

@pytest.fixture(scope="class")
def base_template(base_stack):
    return Template.from_stack(base_stack)

#########################
## LEAF STACK - Domain ##
#########################
@pytest.fixture(scope="class")
def leaf_stack_domain(cdk_app, base_stack):
    return DomainStack(
        cdk_app,
        "TestLeafStack-Domain",
        container_id="test-stack",
        base_stack=base_stack,
    )

@pytest.fixture(scope="class")
def leaf_template_domain(leaf_stack_domain):
    return Template.from_stack(leaf_stack_domain)

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
