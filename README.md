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
```

### Deploy the Stack

There's two stacks, the 'base' stack and the 'leaf' stack. Multiple leaf stacks can/should use the same base stack. Deploy the base stack first, but you shouldn't have to again unless you change something in it.

```bash
source .venv/bin/activate
source vars.env
make cdk-deploy-base
# And after you make any changes:
make cdk-deploy-leaf config-file=./Examples/Valheim-example.yaml
```

## Devel Stuff

See the ContainerManager's [README.md](./ContainerManager/README.md) for info on each stack component, and details in that area.

### Slides

My work has "Day of Innovation" every once in a while, where we can work on whatever we want. Lately I've been choosing this project, and here's the slides from each DoI!

- [2022-08-05 Slides](https://docs.google.com/presentation/d/1WiPHAqWpCft2M5jKnNh05txxDQSTm5wNUTH-mmoHbgw/edit#slide=id.g35f391192_00)
- [2022-12-00 Slides](https://docs.google.com/presentation/d/1PcrMb1X317hyeCmxeNP-6l_UpfHqxDINtxtx3uJujPQ/edit#slide=id.g35f391192_00)
- [2023-10-31 Slides](https://docs.google.com/presentation/d/17rSn7BLDSqF9PRpLHx2mn6WqB7h9m-5fe1JQlgahM58/edit#slide=id.g35ed75ccf_015)
- [2024-02-27 Slides](https://docs.google.com/presentation/d/1XzeM2Bv9nNqtd9tSKaQG3HhUcs1HVuLG5fIK6v1Jodo/edit?usp=sharing)

----

## TODO (In order (not really...))

### Phase 1, MVP

- DONE!

### Phase 2, Optimize and Cleanup

- Minor optimizations:
  - Go through Cloudwatch log Groups, make sure everything has a retention policy by default, and removal policy DESTROY.

## Phase 3, Get ready for Production!

- Configure and streamline the [ECS Cotnaienr Agent](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-agent-config.html). It says you can/should use the [instance user data](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/bootstrap_container_instance.html) to bootstrap it at instance launch time. The list of available config options [is here](https://github.com/aws/amazon-ecs-agent/blob/master/README.md#environment-variables).
  - (Agent is already added, but make sure all the flags we want are set and working.)

- Go through Console and see if everything looks like you want. Check for warnings.
  - For example, EC2 instances say to force IMDSv2 is recommended
  - Make names look nice. I.e Lambda are long and repetitive, not descriptive.


### Phase 4, Add tests

- Add a `__main__` block to all the lambdas so you can call them directly. (Maybe add a script to go out and figure out the env vars for you?). Add argparse to figure out the event/context. Plus timing to see how long each piece takes. (import what it needs in `__main__` too, to keep lambda optimized). This should help with optimizing each piece, and unit testing.
- Good chance to figure out how CDK wants you to design tests. There's a pre-defined folder from `cdk init` in the repo too.
- Add Tags to stack/application, might help with analyzing costs and such.
  - Add Generic stack tags, to help recognize the stack in the console.

### Continue after this

I'm moving longer-term ideas to [DESIGN.md](./DESIGN.md). This section is focused on getting the MVP up and running.

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
          StrictHostKeyChecking no
          UserKnownHostsFile=/dev/null

  # NOTE: THIS ONE MIGHT BE BETTER! I just couldn't get it working on
  #       mine. It might have to do with what ssh client you're using.
  Host *.<DOMAIN_NAME>
      CheckHostIP no
  ```

- If using filezilla:

  - To add the private key, go to `Edit -> Settings -> Connection -> SFTP` and add the key file there.
  - For the URl, put `sftp://<GAME_URL>`. The username is `ec2-user`. Password is blank. Port is 22.
  - Files are stored in `/mnt/efs/<Volumes>`.
