
class TestLeafStackContainerManager:
    def test_minimal_create(self, create_leaf_stack_container_manager, to_template):
        leaf_stack_container_manager = create_leaf_stack_container_manager()
        leaf_template_container_manager = to_template(leaf_stack_container_manager)

        # Add your test logic here
        assert leaf_template_container_manager is not None # TMP
