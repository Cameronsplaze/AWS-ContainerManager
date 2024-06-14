# GameManagement

An AWS manager to run games in the CLOUD!!!

Spins up the EC2 instance when someone connects to it, then spins it back down when they disconnect. RN just minecraft, but plan on expanding to other containers right after.

## Quick Start

First install [aws_cdk](https://docs.aws.amazon.com/cdk/v2/guide/getting_started.html).

### First time setup

```bash
# Setup the venv
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt -r requirements-dev.txt
# Setup the env vars
cp vars.env.example vars.env
nano vars.env # Use the text editor that's better than vim >:)
source vars.env
# Deploy the stack
make cdk-deploy
```

### Every time after setup

```bash
source .venv/bin/activate
source vars.env
# And after you make any changes:
make cdk-deploy
```

## Devel Stuff

See the ContainerManager's [README.md](./ContainerManager/README.md) for info on each stack component, and details in that area.

### Old Design choices

- **Private Subnet with NAT Gateway** vs **Public Subnet**:

    (Went with Public Subnet)

    The idea of this stack was to have ec2 run in a private subnet, and have traffic route through NAT. The problem is you need one NAT per subnet, and they cost ~$32/month EACH. For this project to be usable, it has to cost less than ~$120/year.

    Instead of a NAT, you can also have it in the public subnet, take the pubic IP away, and point a Network Load Balancer to it. Problem is they cost ~$194/year.

    Instead I'm trying out opening the container to the internet directly, but as minimally I can. Also assume it *will* get hacked, but has such little permissions that it can't do anything

- **EFS** vs **EBS**

    (Went with EFS)

    I went with EFS just because I don't want to manage growing / shrinking, plus it integrates with ECS nicely. I want to look at how to make this cheaper when I get MVP working, which might be only having one availability zone by default? Need to look into the cost of it more...

- ECS: **EC2** vs **Fargate**:
  - (Went with EC2. Lambda + Host access makes managing containers cheap and easy.)
  - **EC2**:
    - Pros:
      - Networking `Bridge` mode spins up a couple seconds faster than `awsvpc`, due to the ENI card being attached.
      - Have access to the instance (container host)

  - **Fargate**:
    - Pros:
      - `awsvpc` is considered more secure, since you can use security groups to stop applications from talking. (It says "greater flexibility to control communications between tasks and services at a more granular level". With how this project is organized, each task will have it's own instance anyways. Maybe we can still lock down at the instance level?).
      - `awsvpc` supports both Windows AND Linux containers.

    - Cons:
      - Fargate does not cache images, would have to mirror ANY possible image in ECR. (<https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/pull-behavior.html>).
      - No access to underlying AMI nor the configuration files (`/etc/ecs/ecs.config`)
      - (I don't think?) You can access the instance, which means no SSM to run commands on the host instance. We need this to see if anyone's connected. (The other option is to setup a second container, and monitor the traffic through that, but that eats up task resources for such a simple check. This way it's just a lambda that runs once in a while).

- [**ECS Task StateChange Hook**](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_task_events.html) vs [**ASG Instance StateChange Hook**](https://docs.aws.amazon.com/autoscaling/ec2/userguide/prepare-for-lifecycle-notifications.html):
  - (Went with ASG Hook)
  - **Pros for ASG**:
    - With ECS Task, there's the possibility of the task failing to start and the hook not running. This means you'll be left with an instance that's up, and no management around it to turn it back down. Starting the management with ASG means this won't happen
    - Will be slightly faster. As the task is trying to get placed, the hook to start up the management is happening in parallel. If you used the task hook, they'd be in series.
  - **Cons for ASG**:
    - Part of the management, the lambda cron that checks for connections, will fail if there's no task running. This can happen if it triggers too fast. To get around it, I'll have a Metric + Alarm hooked up to the lambda, and only care about the failure if you get X many in a row. (The management framework being ready TOO fast is a good problem to have anyways).

- Turning off System: Inside lambda-instance-StateChange-hook vs lambda-switch-system:
  - (Went with lambda-instance-StateChange-hook)
  - **Pros for lambda-switch-system**:
    - This is the lambda that turns the system on when route53 sees someone is trying to connect.
    - If you're left in a state where the system is on, but there's no instance, the lambda will trigger every minute all night long. This fixes that by letting the lambda directly turn off the system. (Otherwise if desired_count is already 0, and you SET it to 0, the instance StateChange hook will never trigger).
    - The ASG and ECS Task also spin up/down in the order you expect.
      - Turn on: Instance spins up, triggering Statechange Hook, spins up ECS Task.
      - Turn off: SNS triggers lambda-switch-system, which spins off ECS Task, then spins down instance.
    - The watchdog lambda is only running if there is an active instance, never as the instance is actively spinning up/down.
  - **Pros for lambda-instance-StateChange-hook**:
    - Originally I went with the other option. It turns out that route53 logs can only live in us-east-1, and with how tightly the "lambda-switch-system" lambda was integrated into the system, that meant that 1) the ENTIRE stack would have to be in us-east-1, or 2) You'd need one lambda to forward the request to the second. Alarms can adjust ASG's directly, so by doing this route, there's no need for a "lambda switch system".
    - This also keeps the system straight forward.
    - There's probably  a way to build in the same fail-safe of turning off the system, by adding a alarm to the ASG StateChangeHook too.

### Slides

My work has "Day of Innovation" every once in a while, where we can work on whatever we want. Lately I've been choosing this project, and here's the slides from each DoI!

- [2022-08-05 Slides](https://docs.google.com/presentation/d/1WiPHAqWpCft2M5jKnNh05txxDQSTm5wNUTH-mmoHbgw/edit#slide=id.g35f391192_00)
- [2022-12-00 Slides](https://docs.google.com/presentation/d/1PcrMb1X317hyeCmxeNP-6l_UpfHqxDINtxtx3uJujPQ/edit#slide=id.g35f391192_00)
- [2023-10-31 Slides](https://docs.google.com/presentation/d/17rSn7BLDSqF9PRpLHx2mn6WqB7h9m-5fe1JQlgahM58/edit#slide=id.g35ed75ccf_015)
- [2024-02-27 Slides](https://docs.google.com/presentation/d/1XzeM2Bv9nNqtd9tSKaQG3HhUcs1HVuLG5fIK6v1Jodo/edit?usp=sharing)

----

## TODO (In order (not really...))

### Phase 1, MVP

- Finish the prototype for the Leaf Stack:
  - In case the instance is left on without a cron lambda (left on too long), add an alarm that triggers the BaseStack to email you. I don't see how this can ever trigger, but it'll let me sleep at night.
    - It's there, but email isn't being sent for some reason. Need to debug.

### Phase 2, Optimize and Cleanup

- Minor optimizations:
  - Look closely at the security groups. Especially the container one. Lock them all down to specifically declare both in AND out traffic.
  - Switch external instance ip from ipv4 to ipv6. Will have to also switch dns record from A to AAAA. May also have security group updates to support ipv6. (Switching because ipv6 is cheep/free, and aws is starting to charge for ipv4)
  - Go through Cloudwatch log Groups, make sure everything has a retention policy by default, and removal policy DESTROY.

- Add a `__main__` block to all the lambdas so you can call them directly. (Maybe add a script to go out and figure out the env vars for you?). Add argparse to figure out the event/context. Plus timing to see how long each piece takes. (import what it needs in `__main__` too, to keep lambda optimized). This should help with optimizing each piece, and unit testing.

### Phase 3, Split apart to run multiple games

- Make sure they're locked down from each other too.
- Switch lambda instances to use [aws powertools](https://docs.powertools.aws.dev/lambda/python/latest/). It maybe not installed by default, might have to poke at installing through requirements.txt or lambda layer (not sure which is faster yet).
- SSH: Close port 22 on the EC2. Switch to [one of these](https://repost.aws/questions/QUnV4R9EoeSdW0GT3cKBUR7w/what-is-the-difference-between-ec2-instance-connect-and-session-manager-ssh-connections). They let you still ssh, but keep the port closed. Research which one is better for us.

## Phase 4, Get ready for Production!

- Configure and streamline the [ECS Cotnaienr Agent](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-agent-config.html). It says you can/should use the [instance user data](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/bootstrap_container_instance.html) to bootstrap it at instance launch time. The list of available config options [is here](https://github.com/aws/amazon-ecs-agent/blob/master/README.md#environment-variables).
  - Since this takes place on the instance, things like `ECS_IMAGE_PULL_BEHAVIOR` won't help us. (You loose the cache the second the instance spins down anyways). If this is true, you might have to look into ECR cache storage instead. (I think I want to get the scripts to time startup together before this though. Make sure the extra complexity is worth it.)
    - ECR has a new `Pull through Cache` setting and [cdk construct](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecr.CfnPullThroughCacheRule.html) that might help here. If you use Docker or Github though, you're required to setup auth for it. So make this an optional parameter if this path works out, but definitely test manually if you even see a speedup doing this. ([Blog post here](https://aws.amazon.com/blogs/aws/announcing-pull-through-cache-repositories-for-amazon-elastic-container-registry/))

- Go through Console and see if everything looks like you want. Check for warnings.
  - For example, EC2 instances say to force IMDSv2 is recommended
  - Make names look nice. I.e Lambda are long and repetitive, not descriptive.


### Phase 5, Add tests

- Good chance to figure out how CDK wants you to design tests. There's a pre-defined folder from `cdk init` in the repo too.

----

## SSH Notes

TODO - make more automatic somehow

- Get SSH private key from System Manager Param Storage
- Add it to agent:

  ```bash
  nano ~/.ssh/container-manager
  chmod 600 ~/.ssh/container-manager
  ssh-add ~/.ssh/container-manager
  ```

- SSH into the instance:

  ```bash
  ssh ec2-user@<GAME_URL>
  # Or sometimes:
  ssh -i ~/.ssh/container-manager ec2-user@<GAME_URL>
  ```

- IP will change with each startup. If you have to remove the known host:

  ```bash
  ssh-keygen -R <GAME_URL>
  ```

  **OR** add this to  your local `~/.ssh/config`:

  ```txt
  # This is for ALL games on your domain:
  Host *.<DOMAIN_NAME>
      CheckHostIP no
  ```

- If using filezilla:

  - To add the private key, go to `Edit -> Settings -> Connection -> SFTP` and add the key file there.
  - For the URl, put `sftp://<GAME_URL>`. The username is `ec2-user`. Password is blank. Port is 22.
  - Files are stored in `/mnt/efs/<Volumes>`.

TODO: With Valheim, the `/opt/valheim` directory gives `permission denied` when trying to copy out.

### Long term TODO

Very last:

- (WONT DO FOR THIS PROJECT, but I don't want to loose the notes...) Look at supporting HUGE game servers. For this, you need EKS to run teh game, then a aurora-serverless backend to sink all the containers together. This isn't cheap, and the point of the project is for small servers for a group of friends. It might be a fun thing to expand into last though, once the rest of the project is working as expected, so I'll keep the notes around.
  - Example [here](https://github.com/aws-samples/containerized-game-servers), the "craft" dir is minecraft.
  - They use [eksctl](https://eksctl.io/) to control the cluster.
  - They check how many users are connected [here](https://github.com/aws-samples/containerized-game-servers/blob/master/craft/ci/craft-server/linux-aarch64/serverfiles/monitor_active_game_sessions.sh), but said this was more of a hack to get the demo working. If you want to do it the "kuberneti's" way, you should setup a custom metric and update that. Then scale the nodes based on that metric.
  - From the maintainer of that repo:
    - <https://github.com/aws-samples/containerized-game-servers/tree/master/craft/ci/craft-server/linux-aarch64> is the cdk directory that uses the base image from 1 to build the game server image. You need to run <https://github.com/aws-samples/containerized-game-servers/blob/master/craft/ci/craft-server/linux-aarch64/init.sh>.
    - The game server code is <https://github.com/aws-samples/containerized-game-servers/blob/master/craft/ci/craft-server/linux-aarch64/serverfiles/server.py> that is invoked by <https://github.com/aws-samples/containerized-game-servers/blob/master/craft/ci/craft-server/linux-aarch64/serverfiles/start.sh>. The component that auto-scale game servers is <https://github.com/aws-samples/containerized-game-servers/blob/master/craft/ci/craft-server/linux-aarch64/serverfiles/monitor_active_game_sessions.sh> that runs in the background. It monitors the number of active sessions and increment the k8s deployment size based on the player demand.
    - Other than that I used <https://karpenter.sh/v0.19.2/getting-started/getting-started-with-eksctl/> for the horizontal scaling (adding more nodes) and <https://github.com/aws-samples/containerized-game-servers/blob/master/craft/create_db_schema.sql>  as the database schema. It is currently postgres because the original used sqlite but can easily converted to your favorite dbms. I recommend on using <https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2.html> for hosting the game. Note it will cost ~$40/mon to keep the db up.
    - And this one with the link to the blog <https://aws.amazon.com/blogs/compute/how-to-run-massively-multiplayer-games-with-ec2-spot-using-aurora-serverless/>.
