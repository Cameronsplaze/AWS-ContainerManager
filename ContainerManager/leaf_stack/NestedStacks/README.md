# Nested Stack Components

I broke out the core architecture into [Nested Stacks](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.NestedStack.html), to keep each "chunk" easy to understand and manage. It was becoming a tangled mess of dependencies, and you'd have no idea what would create a circular import otherwise. All of this is still apart of a single "Stack" (The [Main Stack](../README.md#main-stack---mainpy).)

## Dependency Graph

```mermaid
flowchart LR
    %% ID's
    SecurityGroups[SecurityGroups.py]
    Container[Container.py]
    Volumes[Volumes.py]
    EcsAsg[EcsAsg.py]
    Watchdog[Watchdog.py]
    AsgStateChangeHook[AsgStateChangeHook.py]

    %% SecurityGroups - Nothing
    %% Container - Nothing

    %% Volumes
    SecurityGroups --sg_efs_traffic--> Volumes
    Container -- task_definition
                 container
              --> Volumes

    %% EcsAsg
    Container --task_definition--> EcsAsg
    SecurityGroups --sg_container_traffic--> EcsAsg
    Volumes --  efs_file_system
            host_access_point
        --> EcsAsg

    %% Watchdog
    EcsAsg -- auto_scaling_group
              scale_down_asg_action
           --> Watchdog

    %% AsgStateChangeHook
    EcsAsg -- ecs_cluster
              ec2_service
              auto_scaling_group
           --> AsgStateChangeHook
    Watchdog --rule_watchdog_trigger--> AsgStateChangeHook
```

## Components

### SecurityGroups

Factored this out to avoid circular imports. This NestedStack contains the security groups for the leaf_stack.

### Container

This creates the EC2 Task Definition and Container Definition for the stack.

### Volumes

Elastic File System (EFS), is the persistent storage for the leaf_stack. This adds to the container definition, the ability to mount the EFS volume. Backups happen outside of the volume you mount as well, so if someone is able to hack your container somehow, they can't access the backups.

I can't find how to see which AZ a backup is stored in, but [this AWS blog post](https://docs.aws.amazon.com/aws-backup/latest/devguide/disaster-recovery-resiliency.html) *suggests* they're multi-AZ. This is important since if the AZ our single-zone EFS is in goes down, we want the backups in a DIFFERENT AS to let us restore the data. We also don't have to pay for the data being "replicated", beyond the cost of having backups that we're already paying.

### EcsAsg

This creates the Ecs Cluster/Service, AutoScaling Group, and EC2 Launch Template for the ASG. This is basically the stack for managing the single EC2 instance itself. (ASG is used to simplify management, instead of juggling EC2 directly). It also needs the Efs component to mount it TO the instance itself. (It's also mounted to the container already). The reason is if it's mounted to the instance, you can use SFTP and other tools to access the data directly. No need to duplicate the data to S3 and pay extra costs for storage.

### Watchdog

This is the component for checking if anyone is connected to the container. It uses the "ec2 traffic IN" metric for this. We ignore OUT because it's too noisy, and the container could just be sending telemetry out. IN will only detect someone trying to talk to the container, or it downloading updates, which is what we want to know. Once it detects no one is on for *X* many times, it scales down the ASG.

### AsgStateChangeHook

This component will trigger whenever the ASG instance state changes (i.e the one instance either spins up or down). This is used to keep the architecture simple, plus if you update the instance count in the console, everything will naturally update around it.

### Dashboard

This depends on everything, since it shows metrics for everything. Doesn't really add an extra cost, since it's just a dashboard. Easily see what the entire stack is thinking/doing in one place.
