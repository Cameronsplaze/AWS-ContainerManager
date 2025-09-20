
class TestLeafStackDomain:
    def test_minimal_create(self, create_leaf_stack_domain, to_template):
        leaf_stack_domain = create_leaf_stack_domain()
        leaf_template_domain = to_template(leaf_stack_domain)

        # Add your test logic here
        assert leaf_template_domain is not None # TMP
