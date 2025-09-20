
from tests.config_parser.test_base_config_parser import (
    BASE_VPC_MAXAZS,
    LEAF_CONTAINER_PORTS,
)

class TestLeafStackStartSystem:
    def test_minimal_create(self, create_leaf_stack_start_system, to_template):
        leaf_stack_start_system = create_leaf_stack_start_system()
        leaf_template_start_system = to_template(leaf_stack_start_system)

        # Add your test logic here
        assert leaf_template_start_system is not None # TMP

    def test_complex_stack(
            self,
            create_base_stack,
            create_leaf_stack_domain,
            create_leaf_stack_container_manager,
            create_leaf_stack_start_system,
            to_template,
        ):
        """
        Just proving to myself that if I needed to access all stacks
        in a single test, and override both configs, I *could*. (Bad
        test design, but proves the fixtures are flexible enough).
        """
        base_stack = create_base_stack(base_config=BASE_VPC_MAXAZS)
        domain_stack = create_leaf_stack_domain(base_stack=base_stack)
        container_manager_stack = create_leaf_stack_container_manager(
            base_stack=base_stack,
            domain_stack=domain_stack,
            leaf_config=LEAF_CONTAINER_PORTS,
        )
        start_system_stack = create_leaf_stack_start_system(
            base_stack=base_stack,
            domain_stack=domain_stack,
            container_manager_stack=container_manager_stack,
        )
        start_system_template = to_template(start_system_stack)

        assert start_system_template is not None # TMP
