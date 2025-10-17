
import json
from dataclasses import dataclass

import pytest
import aws_cdk as cdk
from aws_cdk.assertions import Template

from ContainerManager.base_stack import BaseStack
from ContainerManager.leaf_stack_group.domain_stack import DomainStack
from ContainerManager.leaf_stack_group.container_manager_stack import ContainerManagerStack
from ContainerManager.leaf_stack_group.start_system_stack import StartSystemStack

from tests.configs import (
    ConfigInfo,
    BASE_MINIMAL,
    LEAF_MINIMAL,
)


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
        template_json: str = json.dumps(template.to_json(), indent=4)
        # Save it to a file. Sometimes the output is too long for the terminal:
        with open("template_output.json", "w", encoding="utf-8") as f:
            f.write(template_json)
        # End everything now, you want to see the output!
        pytest.exit(
            f"Template JSON:\n{template_json}\n",
            returncode=1,
        )
    return _print_template

@dataclass
class CdkApp():
    def __init__(
        self,
        base_config: ConfigInfo=BASE_MINIMAL,
        leaf_config: ConfigInfo=LEAF_MINIMAL,
    ) -> None:
        application_id="test-app"
        container_id="test-stack"
        self.app = cdk.App()
        ## Stacks:
        # Create the base stack:
        self.base_stack = BaseStack(
            self.app,
            "TestBaseStack",
            config=base_config.create_config(),
            application_id_tag_name="ApplicationId",
            application_id_tag_value=application_id
        )
        # Create the domain stack:
        self.domain_stack = DomainStack(
            self.app,
            "TestLeafStack-Domain",
            container_id=container_id,
            base_stack=self.base_stack,
        )
        # Create the container manager stack:
        self.container_manager_stack = ContainerManagerStack(
            self.app,
            "TestLeafStack-ContainerManager",
            base_stack=self.base_stack,
            domain_stack=self.domain_stack,
            application_id=application_id,
            container_id=container_id,
            config=leaf_config.create_config(),
        )
        # Create the start system stack:
        self.start_system_stack = StartSystemStack(
            self.app,
            "TestLeafStack-StartSystem",
            domain_stack=self.domain_stack,
            container_manager_stack=self.container_manager_stack,
            container_id=container_id,
        )
        ## Templates:
        # You can't modify the stack after you create the template (It gets synthed),
        # So create them here:
        self.base_template = Template.from_stack(self.base_stack)
        # Domain Stack
        self.domain_template = Template.from_stack(self.domain_stack)
        # Core Container Manager Stack
        self.container_manager_template = Template.from_stack(self.container_manager_stack)
        # And it's nested stacks:
        self.container_manager_sg_template = Template.from_stack(self.container_manager_stack.sg_nested_stack)
        self.container_manager_container_template = Template.from_stack(self.container_manager_stack.container_nested_stack)
        self.container_manager_volumes_template = Template.from_stack(self.container_manager_stack.volumes_nested_stack)
        self.container_manager_ecs_asg_template = Template.from_stack(self.container_manager_stack.ecs_asg_nested_stack)
        self.container_manager_watchdog_template = Template.from_stack(self.container_manager_stack.watchdog_nested_stack)
        self.container_manager_asg_state_change_hook_template = Template.from_stack(self.container_manager_stack.asg_state_change_hook_nested_stack)
        # Start System Stack
        self.start_system_template = Template.from_stack(self.start_system_stack)

@pytest.fixture(scope="session")
def minimal_app(cdk_app):
    return cdk_app(
        base_config=BASE_MINIMAL,
        leaf_config=LEAF_MINIMAL,
    )

@pytest.fixture(scope="session")
def cdk_app():
    return CdkApp
