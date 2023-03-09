# GameManagement

## Quick Start

An AWS manager to run games in the CLOUD!!!

To create your own stack:

1) Setup access keys. You can figure it out.

2) Run something like:

```bash
aws --region us-west-2 cloudformation deploy --capabilities CAPABILITY_NAMED_IAM --template-file stack.yml --stack-name STACK_NAME_HERE
```

There's params inside `stack.yml` that you can override, but defaults to minecraft for now.

## Devel Stuff

Setup a basic virtual environment, with the different packages:

```bash
sudo apt install python3-pip python3-virtualenv # I think? It's been a bit since I installed this. Don't use the (pip install virtualenv) version though
virtualenv --python=python3 ~/GameManager-env
source ~/GameManager-env/bin/activate
python3 -m pip install boto3 cfn-lint
```

Linting the CF file gives output faster than deploying. First check for errors after editing it:

```bash
cfn-lint stack.yml
```

## Notes

- [Services will always maintain the desired number of tasks and this behavior can't be modified](https://stackoverflow.com/questions/51701260/how-can-i-do-to-not-let-the-container-restart-in-aws-ecs), so it'll be up to the Watchdog, to set desired count back to 0 if the container is failing to start.

## TODO

Quick notes on where I left of, for when I pick this up again one day (Hopefully in order of importance):

- Found ECS / EC2 file. Should be cheaper than fargate?: https://github.com/nathanpeck/ecs-cloudformation/blob/master/cluster/cluster-ec2-private-vpc.yml

- Get EFS working. Just let it talk to EC2 with networking, need to setup permissions. Thought the container was killing itself because of health check, so I disabled it, BUT it might be EFS not connecting that kills it. Can remove health check code after to see if it was also killing it.
  - Basic EFS + Fargate Guide: <https://aws.amazon.com/blogs/containers/developers-guide-to-using-amazon-efs-with-amazon-ecs-and-aws-fargate-part-3/>
  - Complicated but complete example: <https://github.com/aws-samples/drupal-on-ecs-fargate/blob/4258e15cb9d4b013612adfabcd61479e56e04565/template/template.yaml#L470>

- Instead of using lambda + ssm to talk with ecs and see if users are active, would using a custom [ecs healthcheck](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-ecs-taskdefinition-healthcheck.html) work? (Probably not, I'm guessing you can't set the desired count to 0, so a new container would just start up again eventually....)
  - Was thinking lambda + ssm to run netstat inside the ec2 task, BUT that requires the container to have netstat installed, and we want this to work with ANY container the user might throw at us. (Another reason the health check idea is bad too.). Maybe having a separate container and route the traffic through THAT is the way to go.

- The EFS is in the same subnet (public) as EC2 is running in. Should it be private, and edit security groups between the two? Or should we drop the private subnet entirely?

- In the VPC, there's one AWS::EC2::RouteTable for the public side, but each private subnet has their own. Why?? Is this a place we can simplify? Guide I worked from at: <https://dev.to/tiamatt/hands-on-aws-cloudformation-part-4-create-vpc-with-private-and-public-subnets-85d>.

- When a container first starts, it takes a bit since it PULLS a fresh one from Dockerhub. Look into having the container mirrored in ECR, and how to keep that up to date (Maybe cron? Is there a built in automatic way?). Pulls from the same ECR region are insanely fast. (Setup rules since you only ever need one, no backups, and get's nuked if you switch to a new container/game in the same stack. That's what the original repo is for).

- Split apart the VPC stack, from the "GameManager" stack. Each instance of a GameManager, runs a *single* game, and multiple can be tied to the same VPC stack.

- Covert to CDK from cloudfront (Mayyybe do sooner, might solve some other problems by letting us dynamically create subnets, and attach EFS to each one; etc.).

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
