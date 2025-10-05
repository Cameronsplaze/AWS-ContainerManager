
class TestBaseStack:

    def test_vpc_properties(self, create_base_stack, to_template):
        base_stack = create_base_stack()
        base_template = to_template(base_stack)

        ## Make sure there's only one VPC to check:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.assertions.Template.html#resourcewbrcountwbristype-count
        base_template.resource_count_is("AWS::EC2::VPC", 1)
        ## It has basic flags:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.assertions.Template.html#resourcewbrcountwbristype-count
        base_template.has_resource_properties(
            "AWS::EC2::VPC", 
            {
                "EnableDnsSupport": True,
                "EnableDnsHostnames": True,
            }
        )
        ## Has NO NAT Gateways
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.assertions.Template.html#findwbrresourcestype-props
        assert base_template.find_resources(
            "AWS::EC2::NatGateway"
        ) == {}, "NAT Gateways are very expensive"
