# How the Stack Works

TODO: Write this section.

I figured out the dependency graph up to this point, to help when I split pieces off into their own parts. (Each line says `A relies on B`.)

```mermaid
flowchart LR
    # SG-EFS[SG EFS Traffic]
    SG-C[SG Container Traffic]
    # ECS-C[ECS Cluster]
    EC2-R[EC2 Role]
    LT[Launch Template]
    ASG[AutoScaling Group]
    # CP[Capacity Provider]
    # EFS[EFS]
    # EFS-AP[EFS Access Point]
    # EFS-N[EFS Name: str]
    # TaskD[Task Definition]
    Con[EC2 Container]
    # ECS[EC2 Service]
    # LCCC[Lambda Cron: Check Connections]
    # EB-Cron[EventBridge Cron]
    # EB-SC[EventBridge Ec2 StateChange]
    # LSCH[Lambda StateChange Hook]


    SG-EFS <---> SG-C
    LT ---> SG-C
    LT ---> EC2-R
    ASG ---> LT
    CP ---> ASG
    ECS-C ---> CP
    EFS-AP ---> EFS
    EFS ---> SG-EFS
    TaskD <--->|Can split EFS/TD| EFS
    TaskD --->|Can split EFS/TD| EFS-AP
    TaskD ---> EFS-N
    TaskD ---> Con
    Con ---> EFS-N
    ECS ---> ECS-C
    ECS ---> TaskD
    LCCC ---> ASG
    LCCC ---> TaskD
    EB-Cron ---> LCCC
    LSCH ---> ASG
    LSCH ---> EB-Cron
    EB-SC ---> LSCH
    EB-SC ---> ASG
```
