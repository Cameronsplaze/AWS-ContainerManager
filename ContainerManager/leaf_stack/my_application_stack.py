
# For setting up myApplication in the AWS Console:
#    - https://aws.amazon.com/blogs/aws/new-myapplications-in-the-aws-management-console-simplifies-managing-your-application-resources/
#    - https://community.aws/content/2Zx50oqaEnUffu7fnD0oXzxNABb/inside-aws-myapplication-s-toolbox-real-world-scenarios-and-solutions

from aws_cdk import (
    Stack,
    aws_servicecatalogappregistry as appregistry,
)
from constructs import Construct


class MyApplicationStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        application_id: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        ## Create the myApplication:
        self.my_application = appregistry.CfnApplication(
            self,
            "CfnApplication",
            name=application_id,
        )
