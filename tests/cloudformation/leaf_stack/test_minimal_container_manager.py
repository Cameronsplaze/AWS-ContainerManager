
class TestLeafStackContainerManager:
    def test_minimal_create(self, minimal_app):
        leaf_stack_container_manager = minimal_app.container_manager_stack
        leaf_template_container_manager = minimal_app.container_manager_template

        # Add your test logic here
        assert leaf_stack_container_manager is not None # TMP
        assert leaf_template_container_manager is not None # TMP

