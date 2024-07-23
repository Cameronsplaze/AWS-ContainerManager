
# For setting up myApplication in the AWS Console:
#    - https://aws.amazon.com/blogs/aws/new-myapplications-in-the-aws-management-console-simplifies-managing-your-application-resources/
#    - https://community.aws/content/2Zx50oqaEnUffu7fnD0oXzxNABb/inside-aws-myapplication-s-toolbox-real-world-scenarios-and-solutions

from aws_cdk import (
    Stack,
    Tags,
    aws_servicecatalogappregistry as appregistry,
)
from constructs import Construct


class MyApplicationStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        application_id: str,
        container_name_id: str,
        tag_stacks: list[Stack],
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        ###########################
        ### MyApplication STUFF ###
        ###########################
        ## For cost tracking and other things:
        ## This CAN be used on multiple stacks at once, but all the stacks HAVE to be
        ##     in the same region.
        # https://aws.amazon.com/blogs/aws/new-myapplications-in-the-aws-management-console-simplifies-managing-your-application-resources/
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_servicecatalogappregistry.CfnApplication.html
        self.my_application = appregistry.CfnApplication(
            self,
            "CfnApplication",
            name=f"{application_id}-{container_name_id}",
            description=f"Core logic for managing {container_name_id} automatically",
        )

        ## For each stack they pass in, add it to this application
        for stack in tag_stacks:
            # MUST be in the same region as this stack!!
            assert stack.region == self.region, f"Stack '{stack.stack_name}' ({stack.region}) must be in the same region as this stack '{self.stack_name}' ({self.region})"
            ## Adds the 'awsApplication' tag:
            Tags.of(stack).add("awsApplication", self.my_application.attr_arn)
            # Tags.of(stack).add(self.my_application.attr_application_tag_key, self.my_application.attr_application_tag_value)

            ## Add the Stack to myApplication:
            #https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_servicecatalogappregistry.CfnResourceAssociation.html
            stack_resource_association = appregistry.CfnResourceAssociation(
                self,
                "CfnResourceAssociation",
                application=self.my_application.name,
                resource=stack.stack_name,
                resource_type="CFN_STACK",
            )
            # I think this is only required because these are Cfn objects?:
            stack_resource_association.add_dependency(self.my_application)
