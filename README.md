# GameManagement

## Quick Start

An AWS manager to run games in the CLOUD!!!

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

### ContainerManager_VPC Stack

The base stack that the ContainerManager stack links to. This lets you share common resources between containers if you're running more than one. (Why have a VPC for each container?).

### ContainerManager Stack

The actual core logic for managing and running the container.

## TODO (In order)

### Phase 1, MVP

- Move as much as you can (at least the ecs cluster) to the base stack.
  - Obviously the ASG and EC2_Service need to stay in the container stack. There might not be anything else to move over...

- Create a minecraft image based on "itzg/minecraft-server", but with netstat removed. Test if connection testing in lambda still works. It *should* be using netstat installed on the host if I set it up right.

- Get a basic script to spin up/down the ec2 instance + task. This is NOT automating it with DNS yet. Mainly to be a good segway to that, and have a tool to start measuring/optimizing startup time.
  - Basic script is there now, but need to optimize speed up of task with it still.

- Get container to Cache `ECS_IMAGE_PULL_BEHAVIOR: prefer-cached` (if EC2/ECS route): [details here](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/pull-behavior.html#ec2-pull-behavior).

- Container stack is getting complicated. Look into if [NestedStacks](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.NestedStack.html) are worth it? To separate each "chunk" into it's own file. (`./ContainerManager/EFS.py`, etc).

### Phase 2, Automation

- See if you can jump into the ECS Host, and see the docker connection traffic to the containers. (If not, maybe the load balancer can?). Then Create a lambda that can grab that info.

- Have lambda control the ECS container, to spin it up and down.

- Hook up Cloudwatch Cron to lambda. Make sure you need more than one "alarm point" to trigger the lambda. That way if you re-log right when the alarm triggers, it won't trigger the lambda. (Probably just have it check every minute, and you need X in alarm where X is the amount of downtime declared in the config).

- Figure out routing, Route53 stuff. Basically finish off the automation.

### Phase 3, Split apart to run multiple games

- Make sure they're locked down from each other too.
- Go through Console and see if everything looks like you want. Check for warnings.
  - For example, EC2 instances say to force V2 of something...
- Go though cost optimization for everything. There's probably some low-hanging fruit in at *least* EFS
- See how to run multiple of the **same** game. (vanilla and modded MC server). Will use the same ports on VPC maybe? Is changing ports required? Might just work as-is, with different IP's.
- Let `cdk deploy` take a path to a config file. Stores a lot of what's in [vars.env.example](./vars.env.example), on a per-stack basis. Add another way to pass env-vars in through CLI too though, not just file. 1) For passwords. 2) For `EULA=TRUE`, in case we can't have that in the example.
- Go through Cloudwatch Groups, make sure everything has a rentention policy by default
- Add a way to connect with FileZilla to upload files. (Don't go through s3 bucket, you'll pay for extra data storage that way.). Make FTP server optional in config, so you can turn it on when first setting up, then deploy again to disable it.

### Phase 4, Add tests

- Good chance to figure out how CDK wants you to design tests. There's a pre-defined folder from `cdk init` in the repo too.

### Slides

All DoI Slides (Private):

- <https://docs.google.com/presentation/d/1WiPHAqWpCft2M5jKnNh05txxDQSTm5wNUTH-mmoHbgw/edit#slide=id.g35f391192_00>
- <https://docs.google.com/presentation/d/1PcrMb1X317hyeCmxeNP-6l_UpfHqxDINtxtx3uJujPQ/edit#slide=id.g35f391192_00>

### Old Design choices

- Private Subnet with NAT Gateway:
    The idea of this stack was to have ec2 run in a private subnet, and have traffic route through NAT. The problem is you need one NAT per subnet, and they cost ~$32/month EACH. For this project to be usable, it has to cost less than ~$120/year.

    Instead of a NAT, you can also have it in the public subnet, take the pubic IP away, and point a Network Load Balancer to it. Problem is they cost ~$194/year.

    Instead I'm trying out opening the container to the internet directly, but as minimally I can. Also assume it *will* get hacked, but has such little permissions that it can't do anything

- EFS vs EBS
    I went with EFS just because I don't want to manage growing / shrinking, plus it integrates with ECS nicely. I want to look at how to make this cheaper when I get MVP working, which might be only having one availability zone by default? Need to look into the cost of it more...

- ECS: EC2 vs Fargate:

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
