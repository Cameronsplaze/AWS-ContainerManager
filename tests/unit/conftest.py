
import pytest
import json

import aws_cdk as cdk
from aws_cdk.assertions import Template

from ContainerManager.base_stack import BaseStack
from ContainerManager.leaf_stack_group.domain_stack import DomainStack
from ContainerManager.leaf_stack_group.container_manager_stack import ContainerManagerStack
from ContainerManager.leaf_stack_group.start_system_stack import StartSystemStack

from ..config_parser.test_base_config_parser import (
    ConfigInfo,
    BASE_MINIMAL,
    LEAF_MINIMAL,
)

@pytest.fixture
def cdk_app():
    return cdk.App()

@pytest.fixture
def to_template():
    """
    NOTE: Calling `Template.from_stack(stack)` will synthesize the stack. This means you
        CANNOT MODIFY the stack afterwards (including passing it to another stack).
    Therefore, have this convenience function to return the template when you're ready:
    """
    def _to_template(stack) -> Template:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.assertions.Template.html
        return Template.from_stack(stack)
    return _to_template

@pytest.fixture
def print_template():
    """ This method is solely for writing tests, and debugging """
    def _print_template(template):
        template_dict = template.to_json()
        print(json.dumps(template_dict, indent=4))
        assert False, "Failing to see template output."
    return _print_template

################
## BASE STACK ##
################
@pytest.fixture
def create_base_stack(fs, cdk_app):
    def _create_base_stack(base_config: ConfigInfo=BASE_MINIMAL) -> BaseStack:
        # Create the base stack:
        base_stack = BaseStack(
            cdk_app,
            "TestBaseStack",
            config=base_config.create_config(fs),
            application_id_tag_name="ApplicationId",
            application_id_tag_value="test-app"
        )
        return base_stack
    return _create_base_stack


#########################
## LEAF STACK - Domain ##
#########################
@pytest.fixture
def create_leaf_stack_domain(cdk_app, create_base_stack):
    def _create_domain_stack(base_stack=None) -> DomainStack:
        # Default to a minimal base stack if they don`'t provide one:
        if base_stack is None:
            base_stack = create_base_stack()

        # Create the domain stack:
        domain_stack = DomainStack(
            cdk_app,
            "TestLeafStack-Domain",
            container_id="test-stack",
            base_stack=base_stack,
        )
        return domain_stack
    return _create_domain_stack


###################################
## LEAF STACK - ContainerManager ##
###################################
@pytest.fixture
def create_leaf_stack_container_manager(fs, cdk_app, create_base_stack, create_leaf_stack_domain):
    def _create_container_manager_stack(base_stack=None, domain_stack=None, leaf_config=LEAF_MINIMAL) -> ContainerManagerStack:
        # Default to a minimal base stack if they don`'t provide one:
        if base_stack is None:
            base_stack = create_base_stack()
        # Same with domain stack, just default to the basic:
        if domain_stack is None:
            domain_stack = create_leaf_stack_domain(base_stack=base_stack)

        # Finally create the stack:
        container_manager_stack = ContainerManagerStack(
            cdk_app,
            "TestLeafStack-ContainerManager",
            base_stack=base_stack,
            domain_stack=domain_stack,
            application_id="test-app",
            container_id="test-stack",
            config=leaf_config.create_config(fs),
        )
        return container_manager_stack
    return _create_container_manager_stack

##############################
## LEAF STACK - StartSystem ##
##############################

@pytest.fixture
def create_leaf_stack_start_system(cdk_app, create_base_stack, create_leaf_stack_domain, create_leaf_stack_container_manager):
    def _create_start_system_stack(base_stack=None, domain_stack=None, container_manager_stack=None) -> StartSystemStack:
        # Default to a minimal base stack if they don't provide one:
        #   (BOTH other stacks need it below, and need the *same* instance anyways)
        if base_stack is None:
            base_stack = create_base_stack()
        # Same with domain stack, just default to the basic:
        if domain_stack is None:
            domain_stack = create_leaf_stack_domain(base_stack=base_stack)
        # Same with container manager stack:
        if container_manager_stack is None:
            container_manager_stack = create_leaf_stack_container_manager(base_stack=base_stack, domain_stack=domain_stack)

        start_system_stack = StartSystemStack(
            cdk_app,
            "TestLeafStack-StartSystem",
            domain_stack=domain_stack,
            container_manager_stack=container_manager_stack,
            container_id="test-stack",
        )
        return start_system_stack
    return _create_start_system_stack
