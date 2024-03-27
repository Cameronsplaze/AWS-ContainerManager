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

### ContainerManager_VPC Stack

The base stack that the ContainerManager stack links to. This lets you share common resources between containers if you're running more than one. (Why have a VPC for each container?).

### ContainerManager Stack

The actual core logic for managing and running the container.

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

- Turning off System: Inside lambda-instance-StateChange-hook vs lambda-scale-container:
  - (Went with lambda-scale-container)
  - **Pros for lambda-scale-container**:
    - This is the lambda that turns the system on when route53 sees someone is trying to connect.
    - If you're ever left in a case where the lambda watchdog is on, but instance is off, watchdog will error for not being able to find the instance. I'll have an alarm hooked up regardless here. That alarm can trigger ASG directly to turn off the system, and theoretically if you go this route, the system will look straight forward. (Use the ASG Hook to both turn ON the system, and turn it OFF.). The problem with this is if the system ever hits a state where a instance is off, but the watchdog lambda is left on. The alarm will set the desired_count to 0, but because it's already 0, the ASG OFF hook will never trigger. By having all of the "turn off system" logic in a lambda, I can BOTH set the desired_count to 0, AND turn off the EventBridge triggering the watchdog lambda. It'll trigger and shut everything off, even if there's no instance. (Bonus, it has similar permissions anyway since it needs to set desired_count to 1 when route53 triggers it too).
  - **Pros for lambda-instance-StateChange-hook**:
    - The main thing is it makes how each part integrates so simple, I keep second guessing not using this route. The built in fail-safe of the other option is soo desirable though.
    - The other pro is I'd move the task desired_count to this lambda as well. That'd probably fix the "no task placement" error from starting the task too soon too. I then would make both the alarms from the watchdog lambda (num_connections=0, and LambdaErrors), trigger a ASG scale down. If you can get Route53 to trigger a ASG Spin up directly (maybe event bridge?), then there'd be no need for the lambda-switch-system AT ALL. (Though I guess you can maybe get an alert to your email if it triggers too many times? Though a self-correcting system seems more desirable tbh. Plus the lambda-switch-system is nice for both debugging, and optimization testing anyways. We might need it later too for expanding the system).
    - Plus according to [SubscriptionFilter Docs](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_logs.SubscriptionFilter.html), you have to target lambda from route53 anyways, I don't see a way to target ASG like with alarms.

### Slides

My work has "Day of Innovation" every once in a while, where we can work on whatever we want. Lately I've been choosing this project, and here's the slides from each DoI!

- [2022-08-05 Slides](https://docs.google.com/presentation/d/1WiPHAqWpCft2M5jKnNh05txxDQSTm5wNUTH-mmoHbgw/edit#slide=id.g35f391192_00)
- [2022-12-00 Slides](https://docs.google.com/presentation/d/1PcrMb1X317hyeCmxeNP-6l_UpfHqxDINtxtx3uJujPQ/edit#slide=id.g35f391192_00)
- [2023-10-31 Slides](https://docs.google.com/presentation/d/17rSn7BLDSqF9PRpLHx2mn6WqB7h9m-5fe1JQlgahM58/edit#slide=id.g35ed75ccf_015)
- [2024-02-27 Slides](https://docs.google.com/presentation/d/1XzeM2Bv9nNqtd9tSKaQG3HhUcs1HVuLG5fIK6v1Jodo/edit?usp=sharing)

## TODO (In order)

### Phase 1, MVP

- Finish the prototype for the Leaf Stack:
  - Incase the instance is left on without a cron lambda (left on too long), add an alarm that triggers the BaseStack to email you. I don't see how this can ever trigger, but it'll let me sleep at night.
    - If the time limit is 12 hours, see if there's a way to get it to email you EVERY 12 hours.
  - Once base stack is prototyped, figure out logic for spinning up the container when someone tries to connect.

- Finish the prototype for the Base Stack:
  - Figure out passing in host ID, if the domain already exists.
    - I think switch to **public** hosted zone too? That's what it will be if they create one in the console. Plus the docs say "route traffic on internet". Even though the ec2 is in a VPC, we're using it's public IP.
  - Create SNS alarm that emails when specific errors happen. The Leaf stack can hook into this and email when instance is up for too long.


### Phase 2, Optimize and Cleanup

- Container stack is getting complicated. Look into if [NestedStacks](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.NestedStack.html) are worth it? To separate each "chunk" into it's own file. (`./ContainerManager/EFS.py`, etc). As you move each chunk, look into optimizing it:
  - Look closely at the security groups. Especially the container one. Lock them all down to specifically declare both in AND out traffic.

  - Switch external instance ip from ipv4 to ipv6. Will have to also switch dns record from A to AAAA. May also have security group updates to support ipv6. (Switching because ipv6 is cheep/free, and aws is starting to charge for ipv4)

  - Go through Cloudwatch Groups, make sure everything has a retention policy by default

- Add a `__main__` block to all the lambdas so you can call them directly. (Maybe add a script to go out and figure out the env vars for you?). Add argparse to figure out the event/context. Plus timing to see how long each piece takes. (import what it needs in `__main__` too, to keep lambda optimized). This should help with optimizing each piece, and unit testing.

- Look into container to Caching `ECS_IMAGE_PULL_BEHAVIOR: prefer-cached` [details here](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/pull-behavior.html#ec2-pull-behavior).

### Phase 3, Split apart to run multiple games

- Make sure they're locked down from each other too.

- See how to run multiple of the **same** game. (vanilla and modded MC server). Will use the same ports on VPC maybe? Is changing ports required? Might just work as-is, because different instance IP's.

- Let `cdk deploy` take a path to a config file. Stores a lot of what's in [vars.env.example](./vars.env.example), on a per-stack basis. Add another way to pass env-vars in through CLI too though, not just file. 1) For passwords. 2) For `EULA=TRUE`, in case we can't have that in the example.
  - Maybe the stack prefix the same as domain prefix? (`minecraft-java.conf` -> config: `id:minecraft` -> `minecraft.example.com`, you can choose not to have the `*-java`. Stack name would be `minecraft-ContainerManager-Stack`). Have the leaf stack be in an `if`, that only runs if you supply a file. If they just want to update the base stack then, it just won't see the leaf. This still doesn't let you use the same config on multiple stacks though.
    - Maybe pass domain as another arg? `--config <path> --id minecraft`? Then use `id` for both the domain and stack name? You can also store a default in the config file.

    ```python
    # Pseudo-code, maybe something like this will work?
    base_stack = BaseStack(app, "BaseStack", env=env)
    if cdk.args.config_file:
      config = yaml.safe_loads(dk.args.config_file) # Custom loader here instead?
      id_name = cdk.args.id or config.get("id") or raise ValueError("Need to pass id in config or as arg")
      leaf_stack = LeafStack(app, f"{id_name}-LeafStack", env=env config=config, id_name=id_name, base_stack=base_stack)
    ```

    - For loading the config, wrap around `yaml.safe_loads`. Looks like there's a package that supports env vars already [here](https://github.com/mkaranasou/pyaml_env). There's probably others too. Check if this is apart of the yaml standard. Double check how `docker compose` does it too, they'll probably have good syntax too.

## Phase 4, Get ready for Production!

- Add a way to connect with FileZilla to upload files. (Don't go through s3 bucket, you'll pay for extra data storage that way.). Make FTP server optional in config, so you can turn it on when first setting up, then deploy again to disable it.
  - Can data at rest be encrypted if you want filezilla to work? Get it working without encryption first, then test.

- Go through Console and see if everything looks like you want. Check for warnings.
  - For example, EC2 instances say to force IMDSv2 is recommended
  - Make names look nice. I.e Lambda are long and repetitive, not descriptive.

- Go though cost optimization for everything. There's probably some low-hanging fruit
  - For EFS. See if the stack works in a single AZ, and if EFS detects that sets [one_zone](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_efs.FileSystem.html#onezone) automatically.

### Phase 5, Add tests

- Good chance to figure out how CDK wants you to design tests. There's a pre-defined folder from `cdk init` in the repo too.

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
