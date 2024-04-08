# How the Stack Works

## Overview

- The [base_stack.py](./base_stack.py) is common architecture that different containers can share (i.e VPC). Multiple "Leaf Stacks" can point to the same "Base Stack".
- The "Leaf Stack" is a single container. This links to the base stack, and is in-charge of a single container. Inside of the leaf stack:
  - The [domain_info.py](./leaf_stack/domain_info.py) stack has to be it's own stack because route53 logs must live in us-east-1.
  - The [main.py](./leaf_stack/main.py) stack can be in any region you want, and is the core logic.
  - the [link_together.py](./leaf_stack/link_together.py) stack is to avoid a circular dependency between the first two. When it sees a connection in the logs of the `domain_info` stack, it updates the ASG in the `main` stack to spin up the container.

## Diagrams

- Mermaid Docs: <https://mermaid.js.org/syntax/flowchart.html>

TODO: Update Mermaid Chart...
      It is VERY out of date now, but I want to figure out the config logic first.

```mermaid
flowchart TD
    ECS-C[ECS Cluster]
    LT[Launch Template]
    ASG[AutoScaling Group]
    ASG-CP[ASG Capacity Provider]

    EFS-N[EFS Name: param]
    EFS[EFS]
    EFS-AP[EFS Access Point]
    EC2-TD[EC2 Task Definition]

    EC2-C[EC2 Container]
    EC2-S[EC2 Service]

    DOMAIN[Domain Name: param]
    UN-IP[Unavailable IP: param]
    DNS-R[DNS Record]

    M-DM[Metric DimensionMap: param]
    M-NC[Metric Num Connections]
    A-NC[Alarm Num Connections]
    L-NC[Lambda Num Connections]
    R-NC[Rule Num Connections Trigger]

    L-SS[Lambda SwitchSystem]
    L-SCH[Lambda StateChange Hook]
    R-SCT[Rule StateChange Trigger]
    M-NCE[Metric Num Connections Error]
    A-NCE[Alarm Num Connections Error]

    ASG ---> LT
    ASG-CP ---> ASG
    ASG-CP <-.Weak Dep.-> ECS-C

    EFS ---> EFS-AP
    EC2-TD <-.Weak Dep.-> EFS-N
    EC2-TD <-.Weak Dep.-> EFS
    EC2-TD <-.Weak Dep.-> EFS-AP

    EC2-TD ---> EC2-C
    EC2-C <-.Weak Dep.-> EFS-N
    EC2-S ---> ECS-C
    EC2-S ---> EC2-TD

    DNS-R ---> DOMAIN
    DNS-R ---> UN-IP

    M-NC ---> M-DM
    A-NC ---> M-NC
    L-NC ---> ASG
    L-NC ---> EC2-TD
    L-NC ---> M-NC
    L-NC ---> M-NC
    L-NC ---> M-DM
    R-NC ---> L-NC
    A-NC <==Break Here==> L-SS
    L-SS ---> ECS-C
    L-SS ---> EC2-S
    L-SS ---> ASG
    L-SS ---> R-NC
    L-SCH ---> DOMAIN
    L-SCH ---> UN-IP
    L-SCH ---> R-NC
    R-SCT ---> ASG
    R-SCT ---> L-SCH
    M-NCE ---> M-NC
    A-NCE ---> M-NCE
    A-NCE <==Break Here==> L-SS

```

- Put all EFS stuff in 1 stack
- Put all Notify User stuff in one stack
- Look at params, make anything they reference directly in a stack
  - I.e domain_name, unavailable_ip, and ttl are used in two places.
