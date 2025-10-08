
class TestLeafStackDomain:
    def test_minimal_create(self, minimal_app):
        leaf_stack_domain = minimal_app.domain_stack
        leaf_template_domain = minimal_app.domain_template

        # Add your test logic here
        assert leaf_stack_domain is not None # TMP
        assert leaf_template_domain is not None # TMP
