
"""
This module contains the BaseStackDomain class.
"""

from constructs import Construct
from aws_cdk import (
    Stack,
    RemovalPolicy,
    aws_route53 as route53,
    aws_logs as logs,
    aws_iam as iam,
)

# from cdk_nag import NagSuppressions


class BaseStackDomain(Stack):
    """
    Contains shared resources for all leaf stacks.
    Most importantly, the hosted zone.
    """
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        config: dict,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)


        #####################
        ### Route53 STUFF ###
        #####################
        ### These are also imported to other stacks, so save them here:
        self.domain_name = config["Domain"]["Name"]
        ## The instance isn't up, use the "unknown" ip address:
        # https://www.lifewire.com/four-zero-ip-address-818384
        self.unavailable_ip = "0.0.0.0"
        ## Never set TTL to 0, it's not defined in the standard
        # (Since the container is constantly changing, update DNS asap)
        self.dns_ttl = 1
        self.record_type = route53.RecordType.A


        ## Log group for the Route53 DNS logs:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_logs.LogGroup.html
        self.route53_query_log_group = logs.LogGroup(
            self,
            "QueryLogGroup",
            log_group_name=f"/aws/route53/{construct_id}-query-logs",
            # Only need logs to trigger the lambda, don't need long-term:
            retention=logs.RetentionDays.ONE_DAY,
            removal_policy=RemovalPolicy.DESTROY,
        )
        ## You can't grant direct access after creating the sub_hosted_zone, since it needs to
        # write to the log group when you create the zone. AND you can't do a wildcard arn, since the
        # account number isn't in the arn.
        self.route53_query_log_group.grant_write(iam.ServicePrincipal("route53.amazonaws.com"))

        ## The subdomain for the Hosted Zone:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_route53.PublicHostedZone.html
        self.hosted_zone = route53.PublicHostedZone(
            self,
            "HostedZone",
            zone_name=self.domain_name,
            query_logs_log_group_arn=self.route53_query_log_group.log_group_arn,
            comment=f"{construct_id}: DNS query for all containers.",
        )

        ## If you bought a domain through AWS, and have an existing Hosted Zone. We can't
        #   modify it, so we import it and tie ours to the existing one:
        if config["Domain"]["HostedZoneId"]:
            ## Import the existing Route53 Hosted Zone:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_route53.PublicHostedZoneAttributes.html
            self.imported_hosted_zone = route53.PublicHostedZone.from_hosted_zone_attributes(
                self,
                "RootHostedZone",
                hosted_zone_id=config["Domain"]["HostedZoneId"],
                zone_name=self.domain_name,
            )
        else:
            # This is checked in the leaf stack, to see if it needs to add
            # a NS record to this hosted zone.
            self.imported_hosted_zone = None

        #####################
        ### Export Values ###
        #####################
        ## To stop cdk from trying to delete the exports when cdk is deployed by
        ## itself, but still has leaf stacks attached to it.
        # https://blogs.thedevs.co/aws-cdk-export-cannot-be-deleted-as-it-is-in-use-by-stack-5c205b8004b4
        self.export_value(self.hosted_zone.hosted_zone_name_servers)
        self.export_value(self.route53_query_log_group.log_group_arn)
        self.export_value(self.hosted_zone.hosted_zone_id)
        self.export_value(self.route53_query_log_group.log_group_name)
