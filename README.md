# GameManagement

## Quick Start

An AWS manager to run games in the CLOUD!!!

First install [aws_cdk](https://docs.aws.amazon.com/cdk/v2/guide/getting_started.html), and then run `python3 -m pip install -r requirements.txt` to install all the dependencies.

To create your own stack:

```bash
export AWS_PROFILE=your-profile
export AWS_REGION=your-region
make cdk-deploy
```

## Devel Stuff

### GameManager_private Stack

The idea of this stack was to have ec2 run in a private subnet, and have traffic route through NAT. The problem is you need one NAT per subnet, and they cost ~$32/month EACH. For this project to be usable, it has to cost less than ~$120/year.

Instead of a NAT, you can also have it in the public subnet, take the pubic IP away, and point a Network Load Balancer to it. Problem is they cost ~$194/year.

### GameManager_public Stack

Currently the most processing. Exposing the EC2 instance directly to the internet isn't recommended for security, but I'm trying to lock down traffic as much as possible in the VPC/Security Groups. I keep thinking about changing this to Fargate in the future, there's lots of pros/cons to both.

`awsvpc` requires being inside a private subnet for EC2, which goes into the cost mentioned in the private stack. Fargate can use `awsvpc`, need to research if **it** can in a public subnet. (Might switch to if the startup time hit is worth it.).

#### ECS: EC2 vs Fargate

**EC2**:

- Pros:
  - Networking `Bridge` mode spins up a couple seconds faster than `awsvpc`, due to the ENI card being attached.

**Fargate**:

- Pros:
  - `awsvpc` is considered more secure, since you can use security groups to stop applications from talking. (It says "greater flexibility to control communications between tasks and services at a more granular level". With how this project is organized, each task will have it's own instance anyways. Maybe we can still lock down at the instance level?).
  - `awsvpc` supports both Windows AND Linux containers.

- Cons:
  - Fargate does not cache images, would have to mirror ANY possible image in ECR. (<https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/pull-behavior.html>).
  - No access to underlying AMI nor the configuration files (`/etc/ecs/ecs.config`)

## TODO (In order)

### Phase 1, MVP

- Get a basic script to spin up/down the ec2 instance + task. This is NOT automating it with DNS yet. Mainly to be a good segway to that, and have a tool to start measuring/optimizing startup time.

- Get container to Cache `ECS_IMAGE_PULL_BEHAVIOR: prefer-cached` (if EC2/ECS route): [details here](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/pull-behavior.html#ec2-pull-behavior).

- Get EFS working. Just let it talk to EC2 with networking, need to setup permissions. Thought the container was killing itself because of health check, so I disabled it, BUT it might be EFS not connecting that kills it. Can remove health check code after to see if it was also killing it.
  - Basic EFS + Fargate Guide: <https://aws.amazon.com/blogs/containers/developers-guide-to-using-amazon-efs-with-amazon-ecs-and-aws-fargate-part-3/>
  - Complicated but complete example: <https://github.com/aws-samples/drupal-on-ecs-fargate/blob/4258e15cb9d4b013612adfabcd61479e56e04565/template/template.yaml#L470>

### Phase 2, Automation

- See if you can jump into the ECS Host, and see the docker connection traffic to the containers. (If not, maybe the load balancer can?). Then Create a lambda that can grab that info.

- Have lambda control the ECS container, to spin it up and down.

- Figure out routing, Route53 stuff. Basically finish off the automation.

### Phase 3, Split apart to run multiple games

- Make sure they're locked down from each other too.

### Slides

All DoI Slides (Private):

- <https://docs.google.com/presentation/d/1WiPHAqWpCft2M5jKnNh05txxDQSTm5wNUTH-mmoHbgw/edit#slide=id.g35f391192_00>
- <https://docs.google.com/presentation/d/1PcrMb1X317hyeCmxeNP-6l_UpfHqxDINtxtx3uJujPQ/edit#slide=id.g35f391192_00>

### Long term TODO

Very last:

- Look at supporting HUGE game servers. For this, you need EKS to run teh game, then a aurora-serverless backend to sink all the containers together. This isn't cheap, and the point of the project is for small servers for a group of friends. It might be a fun thing to expand into last though, once the rest of the project is working as expected, so I'll keep the notes around.
  - Example [here](https://github.com/aws-samples/containerized-game-servers), the "craft" dir is minecraft.
  - They use [eksctl](https://eksctl.io/) to control the cluster.
  - They check how many users are connected [here](https://github.com/aws-samples/containerized-game-servers/blob/master/craft/ci/craft-server/linux-aarch64/serverfiles/monitor_active_game_sessions.sh), but said this was more of a hack to get the demo working. If you want to do it the "kuberneti's" way, you should setup a custom metric and update that. Then scale the nodes based on that metric.
  - From the maintainer of that repo:
    - <https://github.com/aws-samples/containerized-game-servers/tree/master/craft/ci/craft-server/linux-aarch64> is the cdk directory that uses the base image from 1 to build the game server image. You need to run <https://github.com/aws-samples/containerized-game-servers/blob/master/craft/ci/craft-server/linux-aarch64/init.sh>.
    - The game server code is <https://github.com/aws-samples/containerized-game-servers/blob/master/craft/ci/craft-server/linux-aarch64/serverfiles/server.py> that is invoked by <https://github.com/aws-samples/containerized-game-servers/blob/master/craft/ci/craft-server/linux-aarch64/serverfiles/start.sh>. The component that auto-scale game servers is <https://github.com/aws-samples/containerized-game-servers/blob/master/craft/ci/craft-server/linux-aarch64/serverfiles/monitor_active_game_sessions.sh> that runs in the background. It monitors the number of active sessions and increment the k8s deployment size based on the player demand.
    - Other than that I used <https://karpenter.sh/v0.19.2/getting-started/getting-started-with-eksctl/> for the horizontal scaling (adding more nodes) and <https://github.com/aws-samples/containerized-game-servers/blob/master/craft/create_db_schema.sql>  as the database schema. It is currently postgres because the original used sqlite but can easily converted to your favorite dbms. I recommend on using <https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2.html> for hosting the game. Note it will cost ~$40/mon to keep the db up.
    - And this one with the link to the blog <https://aws.amazon.com/blogs/compute/how-to-run-massively-multiplayer-games-with-ec2-spot-using-aurora-serverless/>.
