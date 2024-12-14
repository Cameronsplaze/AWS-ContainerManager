"""
Cant use `cross_region_references` directly, since base-stack and leaf-stack are basically
two different "apps". This is a custom resource with very similar functionality.
"""

from aws_cdk import(
    aws_logs as logs,
    custom_resources as cr,
)

from constructs import Construct

class ExportCrossZoneVar(cr.AwsCustomResource):
    """
    For exporting values across regions, but still be able to deploy the stack this is declared in after.
    (More details in ./utils/README.md)
    """
    ### Modified/Combined from:
    # - https://stackoverflow.com/questions/59774627/cloudformation-cross-region-reference
    # - https://github.com/pepperize/cdk-ssm-parameters-cross-region/blob/main/src/string-parameter.ts
    # - https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/core/adr/cross-region-stack-references.md
    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            param_name: str,
            param_value: str,
            param_region: str
        ) -> None:
        # In case the value is an int or something:
        param_value = str(param_value)
        self.parameter_arn = f"arn:aws:ssm:{param_region}:{scope.account}:parameter{param_name}"
        ## When Creating the Parameter:
        # https://docs.aws.amazon.com/cdk/api/v1/docs/@aws-cdk_custom-resources.AwsSdkCall.html
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ssm/client/put_parameter.html
        ssm_set_parameter = cr.AwsSdkCall(
            service="ssm",
            action="PutParameter",
            parameters={
                "Name": param_name,
                "Value": param_value,
                "Type": "String",
                "Overwrite": True,
                "Description": f"Cross-Region Parameter, created by {scope.stack_name}",
            },
            region=param_region,
            physical_resource_id=cr.PhysicalResourceId.of(self.parameter_arn),
        )
        ## When nuking the Parameter:
        # https://docs.aws.amazon.com/cdk/api/v1/docs/@aws-cdk_custom-resources.AwsSdkCall.html
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ssm/client/delete_parameter.html
        ssm_delete_parameter = cr.AwsSdkCall(
            service="ssm",
            action="DeleteParameter",
            parameters={
                "Name": param_name,
            },
            region=param_region,
            physical_resource_id=cr.PhysicalResourceId.of(self.parameter_arn),
        )
        # https://docs.aws.amazon.com/cdk/api/v1/docs/@aws-cdk_custom-resources.AwsCustomResourcePolicy.html
        policy = cr.AwsCustomResourcePolicy.from_sdk_calls(
            resources=[self.parameter_arn],
        )
        ### Effectively Calling cr.AwsCustomResource:
        # https://docs.aws.amazon.com/cdk/api/v1/docs/@aws-cdk_custom-resources.AwsCustomResource.html
        super().__init__(
            scope,
            construct_id,
            policy=policy,
            log_retention=logs.RetentionDays.ONE_DAY,
            # on_create: will call on_update anyways.
            on_update=ssm_set_parameter,
            on_delete=ssm_delete_parameter,
        )
