# Leaf Stack - Container Manager Core

This is the core of the Container Manager. It's the AWS Architecture that runs the container, along with spinning it up/down when needed. Multiple `leaf_stack`'s can be deployed together, one for each each container.

## High-Level Architecture

All the leaf stack components *combined*, form the architecture of managing a container. Below shows the **core** logic of just spinning up and down a container:

![picture](../../Resources/AWS-ContainerManager_Basic_Diagram.png)
<!-- Original board: https://sketchboard.me/REucJJtlrBCi#/ -->

**Not an all inclusive diagram**: There's more not shown, like EFS mounted to both the EC2 Task and ASG Instance, SNS Alerts, etc.

The nice thing about this architecture is **all** based around AutoScalingGroup state changes. You can easily change the ASG's `desired_count` in the console if you need, and the rest of the architecture will follow suit (Including matching the ecs task count).

## Dependency Graph

How each of the leaf stack components link together:

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
