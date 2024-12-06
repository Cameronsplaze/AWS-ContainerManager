# Leaf Stack - Container Manager Core

This is the core of the Container Manager. It's the AWS Architecture that runs the container, along with spinning it up/down when needed. Multiple `leaf_stack`'s can be deployed together, one for each each container.

A simple TLDR can be found back one level in [../README.md](../README.md#leaf-stack-summary)

## CDK Architecture

How the leaf stack links together and works:

```mermaid
flowchart LR
    %% Colors:
    %% fill=background, color=font, stroke=border
    classDef blue fill:#C5DEF5,color:#000,stroke:#333;
    classDef red fill:#E99695,color:#000,stroke:#333;
    classDef purple fill:#D4C5F9,color:#000,stroke:#333;
    classDef green fill:#C2E0C6,color:#000,stroke:#333;

    user-connects["🧑‍🤝‍🧑 User Connects"]

    %% DOMAIN STACK SUBGRAPH
    subgraph domain_stack["
    **domain_stack.py**
    (us-east-1)
    "]
        sub-hosted-zone[Sub Hosted Zone]
        query-log-group[Query Log Group]

        sub-hosted-zone --Writes Log--> query-log-group
    end
    class domain_stack blue
    user-connects --DNS Query--> sub-hosted-zone

    %% LINK TOGETHER STACK SUBGRAPH
    subgraph link_together_stack["
    **link_together_stack.py**
    (us-east-1)
    "]
        subscription-filter[Subscription Filter]
        lambda-start-system[Lambda: Start System]

        subscription-filter --trigger--> lambda-start-system
    end
    class link_together_stack green
    query-log-group --if Log matches Filter--> subscription-filter

    %% LEAF STACK SUBGRAPH
    subgraph leaf_stack["
    **leaf_stack.py**
    (Any Region)
    "]
        sns-notify[SNS: Notify]

        subgraph EcsAsg.py
            Asg[AutoScalingGroup]
            Ec2Service[EC2 Service]
            Ec2Instance[EC2 Instance]
            EcsCapacityProvider[ECS Capacity Provider]

            Asg --Starts/Stops--> Ec2Instance
            Asg --Connects--> EcsCapacityProvider
            EcsCapacityProvider --Connects--> Ec2Service
        end
        class EcsAsg.py purple

        subgraph AsgStateChangeHook.py
            events-rule-asg-up[Events Rule: ASG Up]
            events-rule-asg-down[Events Rule: ASG Down]
            lambda-asg-StateChange[Lambda: ASG StateChange]

            events-rule-asg-up --Trigger--> lambda-asg-StateChange
            events-rule-asg-down --Trigger--> lambda-asg-StateChange
        end
        class AsgStateChangeHook.py purple


        Asg --Instance Start--> events-rule-asg-up
        Asg --Instance Stop--> events-rule-asg-down
        events-rule-asg-up --Alert--> sns-notify
        events-rule-asg-down --Alert--> sns-notify
        lambda-asg-StateChange --Updates DNS Record--> sub-hosted-zone
        lambda-asg-StateChange --Updates Task Count--> Ec2Service

        subgraph Volumes.py
            persistent-volume[Persistent Volume]
        end
        class Volumes.py purple
        Ec2Instance --Mounts--> persistent-volume

        subgraph Container.py
            container[Task / Container]
            task-definition[Task Definition]

            task-definition --> container
        end
        class Container.py purple
        Ec2Service --> task-definition
        container --Mounts--> persistent-volume

        subgraph Watchdog.py
            metric-traffic-in[CloudWatch Metric: Traffic]
            metric-traffic-dns[CloudWatch Metric: DNS]
            scale-down-asg-action[Scale Down ASG Action]
            alarm-container-activity[Alarm: Container Activity]
            alarm-instance-up[Alarm: Instance Left Up]
            lambda-break-crash-loop[Lambda: Break Crash Loop]

            metric-traffic-in --Bytes/Second--> alarm-container-activity
            metric-traffic-dns --DNS Query Hit--> alarm-container-activity
            alarm-container-activity --If No Traffic--> scale-down-asg-action
            metric-traffic-in --If ANY traffic for VERY long time--> alarm-instance-up
            alarm-instance-up --If Instance Left Up--> scale-down-asg-action
        end
        class Watchdog.py purple
        sub-hosted-zone --Monitors Info--> metric-traffic-dns
        container --Monitors Info--> metric-traffic-in
        scale-down-asg-action --Stops--> Asg
        alarm-instance-up --Alert--> sns-notify
        container --Crashes--> lambda-break-crash-loop
        lambda-break-crash-loop --Stops--> Asg
        lambda-break-crash-loop --Alert--> sns-notify

    end
    class leaf_stack red
    lambda-start-system --Starts--> Asg
```

## Components

### Domain Stack - [./domain_stack.py](./domain_stack.py)

This sets up the Hosted Zone and DNS for the leaf_stack. This stack MUST be deployed to `us-east-1` since that's where AWS houses Route53.

### Main Stack - [./main.py](./main.py)

This handles seeing if people are connected to the container, along with how to spin DOWN the container when no one is connected. (Spinning up is the Domain Stack, just setting ASG count to one).

This is broken into Nested Stack chunks, to keep each chunk easy to read/manage. For more information, see the [NestedStack's README](./NestedStacks/README.md). It also sets up a SNS for if you just want to subscribe to events of this specific container, and not any others. This stack can be deployed to any region.

### Link Together Stack - [./link_together_stack.py](./link_together_stack.py)

This is what actually spins the ASG up when someone connects. This is it's own stack because it needs Route53 logs from the Domain Stack, so it HAS to be in `us-east-1`. It also needs to know the Main Stacks ASG to spin it up when the query log is hit, so it HAS to be deployed after that stack. We have to make this stack it's own thing then to avoid circular import errors.
