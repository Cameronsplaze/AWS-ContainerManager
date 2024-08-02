# Design of AWS-ContainerManager

This document describes past design choices I've made. If you're looking for the current architecture itself, README's are sprinkled throughout the project detailing the part that they're in. The farther you get from the root of the project, the more specific they should be for that part.

---

## Past Design Choices

### Public vs Private VPC Subnet

(Went with public subnet)

<details>

<summary>Details</summary>

The idea of this stack was to have ec2 run in a private subnet, and have traffic route through NAT. The problem is you need one NAT per subnet, and they cost ~$32/month EACH. For this project to be usable, it has to cost less than ~$120/year.

Instead of a NAT, you can also have it in the public subnet, take the pubic IP away, and point a Network Load Balancer to it. Problem is they cost ~$194/year.

Instead I'm trying out opening the container to the internet directly, but as minimally I can. Also assume it *will* get hacked, but has such little permissions that it can't do anything

</details>


### EBS vs EFS (Storage)

(Went with EFS)

<details>

<summary>Details</summary>

I went with EFS just because I don't want to manage growing / shrinking partitions, plus it integrates with ECS nicely. By making it only exist in one zone by default, it's about the same cost anyways. It gets expensive if you duplicate storage across AZ's, and we don't need that.

</details>

### ECS: EC2 vs Fargate manager

(Went with EC2. Lambda + Host access makes managing containers cheap and easy.)

<details>

<summary>Details</summary>

- **EC2**:
  - Pros:
    - Networking `Bridge` mode spins up a couple seconds faster than `awsvpc`, due to the ENI card being attached in Fargate.
    - Have access to the instance (container host)

- **Fargate**:
  - Pros:
    - `awsvpc` is considered more secure, since you can use security groups to stop applications from talking. (It says "greater flexibility to control communications between tasks and services at a more granular level". With how this project is organized, each task will have it's own instance anyways. Maybe we can still lock down at the instance level?).
    - `awsvpc` supports both Windows AND Linux containers.

  - Cons:
    - Fargate does not cache images, would have to mirror ANY possible image in ECR. (<https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/pull-behavior.html>).
    - No access to underlying AMI nor the configuration files (`/etc/ecs/ecs.config`)
    - (I don't think?) You can access the instance, which means no SSM to run commands on the host instance. We need this to see if anyone's connected. (The other option is to setup a second container, and monitor the traffic through that, but that eats up task resources for such a simple check. This way it's just a lambda that runs once in a while).

</details>

### StateChange Hook: ECS Task vs ASG Instance

([**ECS Task StateChange Hook**](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_task_events.html) vs [**ASG Instance StateChange Hook**](https://docs.aws.amazon.com/autoscaling/ec2/userguide/prepare-for-lifecycle-notifications.html). Went with ASG Hook)

<details>

<summary>Details</summary>

- **Pros for ASG**:
  - With ECS Task, there's the possibility of the task failing to start and the hook not running. This means you'll be left with an instance that's up, and no management around it to turn it back down. Starting the management with ASG means this won't happen
  - Will be slightly faster. As the task is trying to get placed, the hook to start up the management is happening in parallel. If you used the task hook, they'd be in series.
- **Cons for ASG**:
  - Part of the management, the lambda cron that checks for connections, will fail if there's no task running. This can happen if it triggers too fast. To get around it, I'll have a Metric + Alarm hooked up to the lambda, and only care about the failure if you get X many in a row. (The management framework being ready TOO fast is a good problem to have anyways).

</details>

### Turn OFF system: Use ASG Hook vs lambda

(Went with ASG Hook)

<details>

<summary>Details</summary>

- **Lambda (lambda-switch-system)**
  - Pros:
    - This is the lambda that turns the system on when route53 sees someone is trying to connect.
    - If you're left in a state where the system is on, but there's no instance, the lambda will trigger every minute all night long. This fixes that by letting the lambda directly turn off the system. (Otherwise if desired_count is already 0, and you SET it to 0, the instance StateChange hook will never trigger).
  - Cons:
    - Because route53 is only in us-east-1, you'd need a lambda in us-east-1 to forward the request to the second lambda. This is a lot of overhead for a simple task. Using the ASG method has other benefits, along with naturally fits into a multi-region architecture.

- **ASG Hook (lambda-instance-StateChange-hook)**:
  - Pros:
    - Originally I went with the other option. It turns out that route53 logs can only live in us-east-1, and with how tightly the "lambda-switch-system" lambda was integrated into the system, that meant that 1) the ENTIRE stack would have to be in us-east-1, or 2) You'd need one lambda to forward the request to the second. Alarms can adjust ASG's directly, so by doing this route, there's no need for a "lambda switch system".
    - This also keeps the system straight forward. (The same part is in charge of both spinning up *and* down the system).
    - Starting or stopping an instance from the console, will naturally trigger the hook, and manage everything around the instance.

</details>
