
class TestLeafStackStartSystem:
    def test_minimal_create(self, minimal_app):
        leaf_stack_start_system = minimal_app.start_system_stack
        leaf_template_start_system = minimal_app.start_system_template

        # Add your test logic here
        assert leaf_stack_start_system is not None # TMP
        assert leaf_template_start_system is not None # TMP
