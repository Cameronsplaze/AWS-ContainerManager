# GameManagement

## Quick Start

An AWS manager to run games in the CLOUD!!!

To create your own stack:

1) Setup access keys. You can figure it out.

2) Run something like:

```bash
aws --region us-west-2 cloudformation deploy --template-file stack.yml --stack-name STACK_NAME_HERE
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

Quick notes on where I left of, for when I pick this up again one day:

1) I can change the MC server to be public to test connecting to it directly, but in CF, I can't get permissions for letting the container create THIS SPECIFIC log group figured out. I think once that's in though, you can connect to the world by IP.

2) In the VPC, there's one AWS::EC2::RouteTable for the public side, but each private subnet has their own. Why?? Is this a place we can simplify? Guide I worked from at: <https://dev.to/tiamatt/hands-on-aws-cloudformation-part-4-create-vpc-with-private-and-public-subnets-85d>.

3) When a container first starts, it takes a bit since it PULLS a fresh one from Dockerhub. Look into having the container mirrored in ECR, and how to keep that up to date (Maybe cron? Is there a built in automatic way?). Pulls from the same ECR region are insanely fast. (Setup rules since you only ever need one, no backups, and get's nuked if you switch to a new container/game in the same stack. That's what the original repo is for).
