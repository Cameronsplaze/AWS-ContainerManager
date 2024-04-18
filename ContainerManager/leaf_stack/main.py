
import json

from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    Tags,
    aws_lambda,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_iam as iam,
    aws_efs as efs,
    aws_logs as logs,
    aws_autoscaling as autoscaling,
    aws_events as events,
    aws_events_targets as targets,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cloudwatch_actions,
    aws_sns as sns,
)
from constructs import Construct

from ContainerManager.base_stack import ContainerManagerBaseStack
from ContainerManager.leaf_stack.domain_info import DomainStack
# from ContainerManager.utils.get_param import get_param
from ContainerManager.utils.sns_subscriptions import add_sns_subscriptions

## Import Nested Stacks:
from ContainerManager.leaf_stack.NestedStacks.Efs import EfsNestedStack

class ContainerManagerStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, base_stack: ContainerManagerBaseStack, domain_stack: DomainStack, container_name_id: str, config: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.instance_type = config["InstanceType"]
        self.docker_image = config["Container"]["Image"]
        self.docker_ports = config["Container"].get("Ports", [])
        for port in self.docker_ports:
            if len(port) != 1:
                raise ValueError(f"Each port should have only one key-value pair. Got: {port}")

        ###########
        ## Setup Security Groups
        ###########


        ## Security Group for container traffic:
        # TODO: Since someone could theoretically break into the container,
        #        lock down traffic leaving it too.
        #        (Should be the same as VPC sg BEFORE any stacks are added. Maybe have a base SG that both use?)
        self.sg_container_traffic = ec2.SecurityGroup(
            self,
            "sg-container-traffic",
            vpc=base_stack.vpc,
            description="Traffic that can go into the container",
        )
        # Create a name of `<StackName>/<ClassName>/sg-container-traffic` to find it easier:
        Tags.of(self.sg_container_traffic).add("Name", f"{construct_id}/{self.__class__.__name__}/sg-container-traffic")

        for port_info in self.docker_ports:
            protocol, port = list(port_info.items())[0]
            base_stack.sg_vpc_traffic.connections.allow_from(
                ec2.Peer.any_ipv4(),
                ## Dynamically use tcp or udp from:
                # This will create something like: ec2.Port.tcp(25565)
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2.Port.html
                getattr(ec2.Port, protocol.lower())(port),
                description="Game port to allow traffic IN from",
            )

            self.sg_container_traffic.connections.allow_from(
                ec2.Peer.any_ipv4(),           # <---- TODO: Is there a way to say "from outside vpc only"? The sg_vpc_traffic doesn't do it.
                # base_stack.sg_vpc_traffic,
                getattr(ec2.Port, protocol.lower())(port),
                description="Game port to open traffic IN from",
            )

        ###########
        ## Container-specific Notify
        ###########
        ## You can subscribe to this instead if you only care about one of
        ## the containers, and not every.

        ## Create an SNS Topic for notifications:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_sns.Topic.html
        self.sns_notify_topic = sns.Topic(
            self,
            "sns-notify-topic",
            display_name=f"{construct_id}-sns-notify-topic",
        )
        subscriptions = config.get("AlertSubscription", [])
        add_sns_subscriptions(self, self.sns_notify_topic, subscriptions)


        ###########
        ## Setup ECS
        ###########

        ## Cluster for all the games
        # This has to stay in this stack. A cluster represents a single "instance type"
        # sort of. This is the only way to tie the ASG to the ECS Service, one-to-one.
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.Cluster.html
        self.ecs_cluster = ecs.Cluster(
            self,
            "ecs-cluster",
            cluster_name=f"{construct_id}-ecs-cluster",
            vpc=base_stack.vpc,
        )

        ## Permissions for inside the instance:
        self.ec2_role = iam.Role(
            self,
            "ec2-execution-role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            description="This instance's permissions, the host of the container",
        )

        ## Let the instance register itself to a ecs cluster:
        # https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-awsmanpol.html#instance-iam-role-permissions
        self.ec2_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonEC2ContainerServiceforEC2Role"))
        ## Let the instance allow SSM Session Manager to connect to it:
        # https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-getting-started-instance-profile.html
        # https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AmazonSSMManagedEC2InstanceDefaultPolicy.html
        self.ec2_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedEC2InstanceDefaultPolicy"))

        ## For Running Commands (on container creation I think? Keeping just in case we need it later)
        self.ec2_user_data = ec2.UserData.for_linux()
        # self.ec2_user_data.add_commands()

        ## Contains the configuration information to launch an instance, and stores launch parameters
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ec2.LaunchTemplate.html
        self.launch_template = ec2.LaunchTemplate(
            self,
            f"{construct_id}-ASG-LaunchTemplate",
            instance_type=ec2.InstanceType(self.instance_type),
            ## Needs to be an "EcsOptimized" image to register to the cluster
            machine_image=ecs.EcsOptimizedImage.amazon_linux2(),
            # Lets Specific traffic to/from the instance:
            security_group=self.sg_container_traffic,
            user_data=self.ec2_user_data,
            role=self.ec2_role,
        )

        ## A Fleet represents a managed set of EC2 instances:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_autoscaling.AutoScalingGroup.html
        # TODO: Looking in the console "Activity" tab, there's a way to send SNS if instance fails to start/stop.
        #       look into pushing that SNS to at least the base stack's topic.
        self.auto_scaling_group = autoscaling.AutoScalingGroup(
            self,
            "ASG",
            vpc=base_stack.vpc,
            launch_template=self.launch_template,
            # desired_capacity=0,
            min_capacity=0,
            max_capacity=1,
            new_instances_protected_from_scale_in=False,
            ## Notifications:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_autoscaling.AutoScalingGroup.html#notifications
            notifications=[
                # Let base stack sns know if something goes wrong, to flag the admin:
                autoscaling.NotificationConfiguration(topic=base_stack.sns_notify_topic, scaling_events=autoscaling.ScalingEvents.ERRORS),
                # Let users of this specific stack know the same thing:
                autoscaling.NotificationConfiguration(topic=self.sns_notify_topic, scaling_events=autoscaling.ScalingEvents.ERRORS),
            ]
        )

        ## This allows an ECS cluster to target a specific EC2 Auto Scaling Group for the placement of tasks.
        # Can ensure that instances are not prematurely terminated while there are still tasks running on them.
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.AsgCapacityProvider.html
        self.capacity_provider = ecs.AsgCapacityProvider(
            self,
            "AsgCapacityProvider",
            auto_scaling_group=self.auto_scaling_group,
            # To let me delete the stack!!:
            enable_managed_termination_protection=False,
        )
        self.ecs_cluster.add_asg_capacity_provider(self.capacity_provider)
        ## Just to populate information in the console, doesn't change the logic:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.Cluster.html#addwbrdefaultwbrcapacitywbrproviderwbrstrategydefaultcapacityproviderstrategy
        self.ecs_cluster.add_default_capacity_provider_strategy([
            ecs.CapacityProviderStrategy(capacity_provider=self.capacity_provider.capacity_provider_name)
        ])


        ## The details of a task definition run on an EC2 cluster.
        # (Root task definition, attach containers to this)
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.TaskDefinition.html
        self.task_definition = ecs.Ec2TaskDefinition(
            self,
            "task-definition",

            # execution_role= ecs **agent** permissions (Permissions to pull images from ECR, BUT will automatically create one if not specified)
            # task_role= permissions for *inside* the container
        )

        ## EventBridge Rule: Send notification to user when ECS Task spins up or down:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events.Rule.html
        message = events.RuleTargetInput.from_text("\n".join([
            f"Container for '{container_name_id}' has started!",
            f"Connect to it at: '{domain_stack.sub_domain_name}'.",
        ]))
        self.rule_notify_up = events.Rule(
            self,
            "rule-notify-up",
            rule_name=f"{container_name_id}-rule-notify-up",
            description="Let user know when system finishes spinning UP",
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events.EventPattern.html
            event_pattern=events.EventPattern(
                source=["aws.ecs"],
                detail_type=["ECS Task State Change"],
                detail={
                    "clusterArn": [self.ecs_cluster.cluster_arn],
                    # You only care if the TASK starts, or the INSTANCE stops:
                    "lastStatus": ["RUNNING"],
                    "desiredStatus": ["RUNNING"],
                },
            ),
            targets=[
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events_targets.SnsTopic.html
                targets.SnsTopic(
                    base_stack.sns_notify_topic,
                    message=message,
                ),
                targets.SnsTopic(
                    self.sns_notify_topic,
                    message=message,
                ),
            ],
        )

        self.container_log_group = logs.LogGroup(
            self,
            "container-log-group",
            log_group_name=f"/aws/ec2/{construct_id}-ContainerLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )
        # ## Give the task write logging permissions:
        self.container_log_group.grant_write(self.task_definition.task_role)
        
        ## Details for add_container:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.TaskDefinition.html#addwbrcontainerid-props
        ## And what it returns:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.ContainerDefinition.html
        port_mappings = []
        for port_info in self.docker_ports:
            protocol, port = list(port_info.items())[0]
            port_mappings.append(
                ecs.PortMapping(
                    host_port=port,
                    container_port=port,
                    # This will create something like: ecs.Protocol.TCP
                    protocol=getattr(ecs.Protocol, protocol.upper()),
                )
            )
        self.container = self.task_definition.add_container(
            container_name_id.title(),
            image=ecs.ContainerImage.from_registry(self.docker_image),
            port_mappings=port_mappings,
            ## Hard limit. Won't ever go above this
            # memory_limit_mib=999999999,
            ## Soft limit. Container will go down to this if under heavy load, but can go higher
            memory_reservation_mib=4*1024,
            ## Add environment variables into the container here:
            environment=config["Container"].get("Environment", {}),
            ## Logging, straight from:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.LogDriver.html
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="ContainerLogs",
                log_group=self.container_log_group,
            ),
        )


        efs_nested_stack = EfsNestedStack(
            self,
            construct_id,
            description=f"EFS Logic for {construct_id}",
            vpc=base_stack.vpc,
            sg_container_traffic=self.sg_container_traffic,
            task_definition=self.task_definition,
            container=self.container,
            volumes_config=config["Container"].get("Volumes", []),
        )
        self.efs_file_system = efs_nested_stack.efs_file_system

        ## This creates a service using the EC2 launch type on an ECS cluster
        # TODO: If you edit this in the console, there's a way to add "placement template - one per host" to it. Can't find the CDK equivalent rn.
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecs.Ec2Service.html
        self.ec2_service = ecs.Ec2Service(
            self,
            "ec2-service",
            cluster=self.ecs_cluster,
            task_definition=self.task_definition,
            desired_count=0,
            circuit_breaker={
                "rollback": False # Don't keep trying to restart the container if it fails
            },
        )

        ## Scale down ASG if this is ever triggered:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_autoscaling.StepScalingAction.html
        # https://medium.com/swlh/deploy-your-auto-scaling-stack-with-aws-cdk-abae64f8e6b6
        scale_down_asg_action = autoscaling.StepScalingAction(self,
            f"{construct_id}-scale-down-asg-action",
            auto_scaling_group=self.auto_scaling_group,
            adjustment_type=autoscaling.AdjustmentType.EXACT_CAPACITY,
        )
        scale_down_asg_action.add_adjustment(adjustment=0, lower_bound=0)

        ###########
        ## Setup Lambda WatchDog Timer
        ###########
        self.metric_namespace = construct_id
        self.metric_unit = cloudwatch.Unit.COUNT
        self.metric_dimension_map = {
            "ContainerNameID": container_name_id,
        }
        ## Custom Metric for the number of connections
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Metric.html
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/cloudwatch/client/put_metric_data.html
        self.metric_num_connections = cloudwatch.Metric(
            namespace=self.metric_namespace,
            metric_name="Metric-NumConnections",
            dimensions_map=self.metric_dimension_map,
            label="Number of Connections",
            unit=self.metric_unit,
            # If multiple requests happen in a period, this takes the higher of the two.
            # This way BOTH have to be zero for it to count as an alarm trigger.
            # (And it's still accurate, multiple of the same value will just be that value)
            statistic=cloudwatch.Stats.MAXIMUM,
            # It costs $0.30 to create this metric, but then the first million API
            # requests are free. Since this only happens when the container is up, we're fine.
            period=Duration.minutes(1),
        )
        ## Trigger if 0 people are connected for too long:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Metric.html#createwbralarmscope-id-props
        self.alarm_num_connections = self.metric_num_connections.create_alarm(
            self,
            "Alarm-NumConnections",
            alarm_name=f"{construct_id}-Alarm-NumConnections",
            alarm_description="Trigger if 0 people are connected for too long",
            evaluation_periods=config.get("MinutesWithoutPlayers", 5),
            threshold=0,
            comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.MISSING,
        )
        ## Call this if switching to ALARM:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Alarm.html#addwbralarmwbractionactions
        self.alarm_num_connections.add_alarm_action(
            cloudwatch_actions.AutoScalingAction(scale_down_asg_action)
        )

        ## Lambda, count the number of connections and pass to CloudWatch Alarm
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_lambda.Function.html
        self.lambda_watchdog_num_connections = aws_lambda.Function(
            self,
            "lambda-watchdog-num-connections",
            description=f"{container_name_id}-Watchdog: Counts the number of connections to the container, and passes it to a CloudWatch Alarm.",
            code=aws_lambda.Code.from_asset("./ContainerManager/leaf_stack/lambda/watchdog-num-connections/"),
            handler="main.lambda_handler",
            runtime=aws_lambda.Runtime.PYTHON_3_12,
            timeout=Duration.seconds(30),
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "ASG_NAME": self.auto_scaling_group.auto_scaling_group_name,
                "TASK_DEFINITION": self.task_definition.family,
                "METRIC_NAMESPACE": self.metric_namespace,
                "METRIC_NAME": self.metric_num_connections.metric_name,
                # Convert from an Enum, to a string that boto3 expects. (Words must have first letter
                #   capitalized too, which is what `.title()` does. Otherwise they'd be all caps).
                "METRIC_UNIT": self.metric_unit.value.title(),
                "METRIC_DIMENSIONS": json.dumps(self.metric_dimension_map),
            },
        )
        # Just like the other lambda, check and find the running instance:
        self.lambda_watchdog_num_connections.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["autoscaling:DescribeAutoScalingGroups"],
                resources=["*"],
            )
        )
        # Give it permissions to send commands to the instance host:
        self.lambda_watchdog_num_connections.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ssm:SendCommand"],
                # No clue what the instance ID will be, so lock it to the ASG:
                resources=["*"],
                conditions={
                    "StringEquals": {
                        "aws:ResourceTag/aws:autoscaling:groupName": self.auto_scaling_group.auto_scaling_group_name,
                    }
                },
            )
        )
        self.lambda_watchdog_num_connections.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ssm:SendCommand"],
                resources=[f"arn:aws:ssm:{self.region}::document/AWS-RunShellScript"],
            )
        )
        self.lambda_watchdog_num_connections.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ssm:GetCommandInvocation"],
                resources=[f"arn:aws:ssm:{self.region}:{self.account}:*"],
            )
        )
        # Give it permissions to push metric data:
        self.lambda_watchdog_num_connections.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["cloudwatch:PutMetricData"],
                resources=["*"],
                conditions={
                    "StringEquals": {
                        "cloudwatch:namespace": self.metric_namespace,
                    }
                }
            )
        )

        ## EventBridge Rule to trigger lambda every minute, to see how many are using the container
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events.Rule.html
        self.rule_watchdog_trigger = events.Rule(
            self,
            "rule-watchdog-trigger",
            rule_name=f"{container_name_id}-rule-watchdog-trigger",
            description="Trigger Watchdog Lambda every minute, to see how many are using the container",
            schedule=events.Schedule.rate(Duration.minutes(1)),
            targets=[
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events_targets.LambdaFunction.html
                targets.LambdaFunction(self.lambda_watchdog_num_connections),
            ],
            # Start disabled, self.lambda_watchdog_num_connections will enable it when instance starts up 
            enabled=False,
        )

        ## Lambda function to update the DNS record:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_lambda.Function.html
        self.lambda_asg_state_change_hook = aws_lambda.Function(
            self,
            "lambda-asg-StateChange-hook",
            description=f"{container_name_id}-ASG-StateChange: Triggered by ec2 state changes. Starts the management logic",
            code=aws_lambda.Code.from_asset("./ContainerManager/leaf_stack/lambda/instance-StateChange-hook/"),
            handler="main.lambda_handler",
            runtime=aws_lambda.Runtime.PYTHON_3_12,
            timeout=Duration.seconds(30),
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "HOSTED_ZONE_ID": domain_stack.sub_hosted_zone.hosted_zone_id,
                "DOMAIN_NAME": domain_stack.sub_domain_name,
                "UNAVAILABLE_IP": domain_stack.unavailable_ip,
                "UNAVAILABLE_TTL": str(domain_stack.unavailable_ttl),
                "WATCH_INSTANCE_RULE": self.rule_watchdog_trigger.rule_name,
                "ECS_CLUSTER_NAME": self.ecs_cluster.cluster_name,
                "ECS_SERVICE_NAME": self.ec2_service.service_name,
            },
        )
        self.lambda_asg_state_change_hook.add_to_role_policy(
            iam.PolicyStatement(
                # NOTE: these are on the list of actions that CANNOT be locked down
                #   in ANY way. You *must* use a wild card, and conditions *don't* work 🙄
                effect=iam.Effect.ALLOW,
                actions=[
                    # To get the IP of a new instance:
                    "ec2:DescribeInstances",
                    # To make sure no other instances are starting up:
                    "autoscaling:DescribeAutoScalingGroups",
                ],
                resources=["*"],
            )
        )
        # Give it permissions to update the service desired_task:
        self.lambda_asg_state_change_hook.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ecs:UpdateService",
                    "ecs:DescribeServices",
                ],
                resources=[self.ec2_service.service_arn],
            )
        )
        ## Let it update the DNS record of this stack:
        self.lambda_asg_state_change_hook.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["route53:ChangeResourceRecordSets"],
                resources=[domain_stack.sub_hosted_zone.hosted_zone_arn],
            )
        )
        ## Let it enable/disable the cron rule for counting connections:
        self.lambda_asg_state_change_hook.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "events:EnableRule",
                    "events:DisableRule",
                ],
                resources=[self.rule_watchdog_trigger.rule_arn],
            )
        )

        ## EventBridge Rule: This is actually what hooks the Lambda to the ASG/Instance.
        #    Needed to keep the management in sync with if a container is running.
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events.Rule.html
        self.rule_asg_state_change_trigger = events.Rule(
            self,
            "rule-ASG-StateChange-hook",
            rule_name=f"{container_name_id}-rule-ASG-StateChange-hook",
            description="Trigger Lambda whenever the ASG state changes, to keep DNS in sync",
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events.EventPattern.html
            event_pattern=events.EventPattern(
                source=["aws.autoscaling"],
                # "EC2 Instance Launch Successful" -> FINISHES spinning up (has an ip now)
                # "EC2 Instance-terminate Lifecycle Action" -> STARTS to spin down (shorter
                #                          wait time than "EC2 Instance Terminate Successful").
                detail_type=["EC2 Instance Launch Successful", "EC2 Instance-terminate Lifecycle Action"],
                detail={
                    "AutoScalingGroupName": [self.auto_scaling_group.auto_scaling_group_name],
                },
            ),
            targets=[
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events_targets.LambdaFunction.html
                targets.LambdaFunction(self.lambda_asg_state_change_hook),
            ],
        )
        ## Same thing, but notify user when task spins down finally:
        ##   (Can't combine with above target, since we care about different 'detail_type'.
        ##    Don't want to spam the user sadly.)
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events.Rule.html
        message = events.RuleTargetInput.from_text(f"Container for '{container_name_id}' has stopped.")
        self.rule_notify_down = events.Rule(
            self,
            "rule-notify-down",
            rule_name=f"{container_name_id}-rule-notify-up-down",
            description="Let user know when system finishes spinning down",
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events.EventPattern.html
            event_pattern=events.EventPattern(
                source=["aws.autoscaling"],
                detail_type=["EC2 Instance-terminate Lifecycle Action"],
                detail={
                    "AutoScalingGroupName": [self.auto_scaling_group.auto_scaling_group_name],
                },
            ),
            targets=[
                # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_events_targets.SnsTopic.html
                targets.SnsTopic(base_stack.sns_notify_topic, message=message),
                targets.SnsTopic(self.sns_notify_topic, message=message),
            ],
        )

        ## Grab existing metric for Lambda fail alarm
        # https://bobbyhadz.com/blog/cloudwatch-alarm-aws-cdk
        ## Something like this:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_lambda.Function.html#metricwbrerrorsprops
        self.metric_watchdog_errors = self.lambda_watchdog_num_connections.metric_errors(
            label="Number of Watchdog Errors",
            unit=cloudwatch.Unit.COUNT,
            # If multiple requests happen in a period, and one isn't an error,
            # use that one.
            statistic=cloudwatch.Stats.MINIMUM,
            period=Duration.minutes(1),
        )
        self.alarm_watchdog_errors = self.metric_watchdog_errors.create_alarm(
            self,
            "Alarm-Watchdog-Errors",
            alarm_name=f"{construct_id}-Alarm-Watchdog-Errors",
            alarm_description="Trigger if the Lambda Watchdog fails too many times",
            # Must be in alarm this long consecutively to trigger:
            evaluation_periods=3,
            # What counts as an alarm (ANY error here):
            threshold=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.MISSING,
        )

        ## Call this if switching to ALARM:
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_cloudwatch.Alarm.html#addwbralarmwbractionactions
        self.alarm_watchdog_errors.add_alarm_action(
            cloudwatch_actions.AutoScalingAction(scale_down_asg_action)
        )
