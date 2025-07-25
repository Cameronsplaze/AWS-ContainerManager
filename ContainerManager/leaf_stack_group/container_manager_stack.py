
"""
This is the logic for ContainerManagerStack.
"""

import re

from aws_cdk import (
    Stack,
    aws_sns as sns,
)
from constructs import Construct
from cdk_nag import NagSuppressions

from ContainerManager.base_stack import BaseStack
from ContainerManager.leaf_stack_group.domain_stack import DomainStack
# from ContainerManager.utils.get_param import get_param
from ContainerManager.utils.sns_subscriptions import add_sns_subscriptions

## Import Nested Stacks:
from ContainerManager.leaf_stack_group import NestedStacks


class ContainerManagerStack(Stack):
    """
    This stack is the core manager for the container. It is broken
    into nested stacks for easier management of each component.
    """
    ## This makes the stack names of NestedStacks MUCH more readable:
    # (From: https://github.com/aws/aws-cdk/issues/18053 and https://github.com/aws/aws-cdk/issues/19099)
    def get_logical_id(self, element):
        if "NestedStackResource" in element.node.id:
            match = re.search(r'([a-zA-Z0-9]+)\.NestedStackResource', element.node.id)
            if match:
                # Returns "VolumesNestedStack" instead of "VolumesNestedStackVolumesNestedStackResource..."
                return match.group(1)
            # Fail fast. If the logical_id ever changes on a existing stack, you replace everything and might loose data.
            raise RuntimeError(f"Could not find 'NestedStackResource' in {element.node.id}. Did a CDK update finally fix NestedStack names?")
        return super().get_logical_id(element)

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        base_stack: BaseStack,
        domain_stack: DomainStack,
        application_id: str,
        container_id: str,
        config: dict,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        ###############################
        ## Container-specific Notify ##
        ###############################
        ## You can subscribe to this instead if you only care about one of
        ## the containers, and not every.

        ## Create an SNS Topic for notifications:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_sns.Topic.html
        self.sns_notify_topic = sns.Topic(
            self,
            "SnsNotifyTopic",
            display_name=f"{construct_id}-sns-notify-topic",
            enforce_ssl=True,
        )
        subscriptions = config.get("AlertSubscription", [])
        add_sns_subscriptions(self, self.sns_notify_topic, subscriptions)


        #####################
        ## Core Leaf Stack ##
        #####################

        ### All the info for the Security Group Stuff
        self.sg_nested_stack = NestedStacks.SecurityGroups(
            self,
            description=f"Security Group Logic for {construct_id}",
            leaf_construct_id=construct_id,
            vpc=base_stack.vpc,
            container_id=container_id,
            container_ports_config=config["Container"]["Ports"],
        )

        ### All the info for the Container Stuff
        self.container_nested_stack = NestedStacks.Container(
            self,
            description=f"Container Logic for {construct_id}",
            leaf_construct_id=construct_id,
            container_id=container_id,
            container_config=config["Container"],
        )

        ### All the info for Volumes Stuff
        self.volumes_nested_stack = NestedStacks.Volumes(
            self,
            description=f"Volume Logic for {construct_id}",
            vpc=base_stack.vpc,
            task_definition=self.container_nested_stack.task_definition,
            container=self.container_nested_stack.container,
            volumes_config=config["Volumes"],
            sg_efs_traffic=self.sg_nested_stack.sg_efs_traffic,
        )

        ### All the info for the ECS and ASG Stuff
        self.ecs_asg_nested_stack = NestedStacks.EcsAsg(
            self,
            description=f"Ec2Service Logic for {construct_id}",
            leaf_construct_id=construct_id,
            vpc=base_stack.vpc,
            ssh_key_pair=base_stack.ssh_key_pair,
            base_stack_sns_topic=base_stack.sns_notify_topic,
            leaf_stack_sns_topic=self.sns_notify_topic,
            task_definition=self.container_nested_stack.task_definition,
            ec2_config=config["Ec2"],
            sg_container_traffic=self.sg_nested_stack.sg_container_traffic,
            efs_file_systems=self.volumes_nested_stack.efs_file_systems,
        )

        ### All the info for the Watchdog Stuff
        self.watchdog_nested_stack = NestedStacks.Watchdog(
            self,
            description=f"Watchdog Logic for {construct_id}",
            leaf_construct_id=construct_id,
            container_id=container_id,
            watchdog_config=config["Watchdog"],
            auto_scaling_group=self.ecs_asg_nested_stack.auto_scaling_group,
            metric_volume_bytes_out_per_second=self.volumes_nested_stack.bytes_out_per_second,
            base_stack_sns_topic=base_stack.sns_notify_topic,
            leaf_stack_sns_topic=self.sns_notify_topic,
            ecs_cluster=self.ecs_asg_nested_stack.ecs_cluster,
        )

        ### All the info for the Asg StateChange Hook Stuff
        self.asg_state_change_hook_nested_stack = NestedStacks.AsgStateChangeHook(
            self,
            description=f"AsgStateChangeHook Logic for {construct_id}",
            container_id=container_id,
            domain_stack=domain_stack,
            auto_scaling_group=self.ecs_asg_nested_stack.auto_scaling_group,
            base_stack_sns_topic=base_stack.sns_notify_topic,
            leaf_stack_sns_topic=self.sns_notify_topic,
        )

        ######################
        ## Dashboard Stuff ###
        ######################
        if config["Dashboard"]["Enabled"]:
            self.dashboard_nested_stack = NestedStacks.Dashboard(
                self,
                description=f"Dashboard Logic for {construct_id}",
                application_id=application_id,
                container_id=container_id,
                main_config=config,

                domain_stack=domain_stack,
                container_nested_stack=self.container_nested_stack,
                volumes_nested_stack=self.volumes_nested_stack,
                ecs_asg_nested_stack=self.ecs_asg_nested_stack,
                watchdog_nested_stack=self.watchdog_nested_stack,
                asg_state_change_hook_nested_stack=self.asg_state_change_hook_nested_stack,
            )

        #####################
        ### cdk_nag stuff ###
        #####################
        # Do at very end, they have to "suppress" after everything's created to work.
        NagSuppressions.add_resource_suppressions(self.sns_notify_topic, [
            {
                "id": "AwsSolutions-SNS2",
                "reason": "KMS is costing ~3/month, and this isn't sensitive data anyways.",
            },
        ])
