# Leaf Stack - Container Manager Core

This is the core of the Container Manager. It's the AWS Architecture that runs the container, along with spinning it up/down when needed. Multiple `leaf_stack`'s can be deployed together, one for each each container.

## CDK Architecture

How the leaf stack links together and works:

```mermaid
flowchart LR
    user-connects[User Connects]
    subgraph "domain_stack.py (us-east-1)"
        sub-hosted-zone[Sub Hosted Zone]
        query-log-group[Query Log Group]

        sub-hosted-zone --Writes Log--> query-log-group
    end
    user-connects --DNS Query--> sub-hosted-zone

    subgraph "link_together_stack.py (us-east-1)"
        subscription-filter[Subscription Filter]
        lambda-start-system[Lambda: Start System]

        subscription-filter --trigger--> lambda-start-system
    end
    query-log-group --if Log matches Filter--> subscription-filter

    subgraph "leaf_stack.py (any region)"
        sns-notify[SNS: Notify]

        subgraph EcsAsg.py
            Asg[AutoScalingGroup]
            Ec2Service[EC2 Service]
            Ec2Instance[EC2 Instance]

            Asg --Starts/Stops--> Ec2Instance
        end

        subgraph AsgStateChangeHook.py
            events-rule-asg-up[Events Rule: ASG Up]
            events-rule-asg-down[Events Rule: ASG Down]
            lambda-asg-StateChange[Lambda: ASG StateChange]

            events-rule-asg-up --Trigger--> lambda-asg-StateChange
            events-rule-asg-down --Trigger--> lambda-asg-StateChange
        end

        Asg --Instance Start--> events-rule-asg-up
        Asg --Instance Stop--> events-rule-asg-down
        events-rule-asg-up --> sns-notify
        events-rule-asg-down --> sns-notify
        lambda-asg-StateChange --Updates DNS Record--> sub-hosted-zone
        lambda-asg-StateChange --Updates Task Count--> Ec2Service

        subgraph Volumes.py
            persistent-volume[Persistent Volume]
        end
        Ec2Instance --Mounts--> persistent-volume

        subgraph Container.py
            container[Container]
            task-definition[Task Definition]

            task-definition --> container
        end
        Ec2Service --> task-definition
        container --Mounts--> persistent-volume

    end
    lambda-start-system --Starts--> Asg
```

```mermaid
flowchart LR
    subgraph Servers
        Server1
        Server2
    end
    subgraph Storage
        disk1[("Disk1")]
        disk2[("Disk2")]
    end
    subgraph Network
        subgraph TEST
            disk3[("Disk3")]
        end
        VPN
        Internet
    end
    web["🕸️ Website"]
    users["🧑‍🤝‍🧑 Users"]
    Servers --> Storage
    Servers --> VPN
    VPN --> Internet
    Internet --> web
    users --> web
    %% Google brand
    classDef blue fill:#4285f4,color:#fff,stroke:#333;
    classDef red fill:#db4437,color:#fff,stroke:#333;
    classDef yellow fill:#f4b400,color:#fff,stroke:#333;
    classDef green fill:#0f9d58,color:#fff,stroke:#333;
    class Servers,Storage blue
    class web green
    class Network red
    class users yellow
    class TEST green
```

```mermaid
flowchart LR
    %% ID's
    domain_stack[domain_stack.py]
    main[main.py]
    link_together_stack[link_together_stack.py]

    domain_stack -- sub_domain_name
                    sub_hosted_zone
                    unavailable_ip
                    dns_ttl
                    record_type
                 --> main

    domain_stack -- route53_query_log_group
                        sub_domain_name
                 --> link_together_stack

    main -- auto_scaling_group
                watchdog_nested_stack (All metric info)
         --> link_together_stack
```

## Components

### Domain Stack - [./domain_stack.py](./domain_stack.py)

This sets up the Hosted Zone and DNS for the leaf_stack. This stack MUST be deployed to `us-east-1` since that's where AWS houses Route53.

### Main Stack - [./main.py](./main.py)

This handles seeing if people are connected to the container, along with how to spin DOWN the container when no one is connected. (Spinning up is the Domain Stack, just setting ASG count to one).

This is broken into Nested Stack chunks, to keep each chunk easy to read/manage. For more information, see the [NestedStack's README](./NestedStacks/README.md). It also sets up a SNS for if you just want to subscribe to events of this specific container, and not any others. This stack can be deployed to any region.

### Link Together Stack - [./link_together_stack.py](./link_together_stack.py)

This is what actually spins the ASG up when someone connects. This is it's own stack because it needs Route53 logs from the Domain Stack, so it HAS to be in `us-east-1`. It also needs to know the Main Stacks ASG to spin it up when the query log is hit, so it HAS to be deployed after that stack. We have to make this stack it's own thing then to avoid circular import errors.
