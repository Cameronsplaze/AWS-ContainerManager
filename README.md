# GameManagement

Run Minecraft, Valheim, or any container in AWS!

This CDK project spins up the container when someone connects, then spins it back down when they're done automatically. It's a great way to save money on your game servers, without opening your home network to the world.

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

There's two stacks, the 'base' stack and the 'leaf' stack. Multiple leaf stacks can/should use the **same** base stack. Deploy the base stack first, but you shouldn't have to again unless you change something in it.

### Base Stack

The config options are in `./base-stack-config.yaml`. Info on each option is in "ContainerManager/README.md/..." (**TODO**).

If you need a `HostedZoneId`, you can [buy a domain from AWS](https://aws.amazon.com/getting-started/hands-on/get-a-domain/).

For a quickstart, just run:

```bash
# `source` if new shell
source .venv/bin/activate
source vars.env
# Actually deploy:
make cdk-deploy-base
```

### Leaf Stack

The config examples are in `./Examples/*-example.yaml`. Info on each config option is in "./Examples/README.md/..." (**TODO**). For a quickstart, just run:

```bash
# `source` if new shell
source .venv/bin/activate
source vars.env
# Edit the config to what you want:
cp ./Examples/Minecraft-example.yaml ./Minecraft.yaml
nano ./Minecraft.yaml
# Actually deploy:
make cdk-deploy-leaf config-file=./Minecraft.yaml
```

### Connecting to the Container

Your game should be live at `<FileName>.<DOMAIN_NAME>`! (So `Minecraft.<DOMAIN_NAME>` in this case. No ".yaml")

> [!NOTE]
> It takes ~2 minutes for the game to spin up when it sees the first DNS connection come in. Just spam refresh.

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

- Go through Console and see if everything looks like you want. Check for warnings.

- Write up guide on moving files into EFS if a stack already existed
  - Check if you can import EFS into the stack, I don't think you can.
  - Check Data Sync, it keeps you in network. (Move from the previous stacks EFS into the new stack)
  - Just use SFTP with Filezilla or something. Most expensive but easiest.

### Phase 4, Add tests

- Using pytest. Will also expand this to get timings of how long each part of the stack takes to spin up/down when someone connects.
  - [cdk-nag](https://github.com/cdklabs/cdk-nag) can flag some stuff
- Add Tags to stack/application, might help with analyzing costs and such.
  - Add Generic stack tags, to help recognize the stack in the console.

### Continue after this

I'm moving longer-term ideas to [DESIGN.md](./DESIGN.md). This section is focused on getting the MVP up and running.

----

## SSH Notes

TODO - make more automatic somehow

- Get SSH private key from System Manager (SSM) Param Storage
- Add it to agent:

  ```bash
  nano ~/.ssh/container-manager # Paste key from SSM
  chmod 600 ~/.ssh/container-manager
  ssh-add ~/.ssh/container-manager
  ```

- Add this to your `~/.ssh/config`:

  **NOTE**: The DOMAIN_NAME must be all lowercase! Otherwise it won't be case-insensitive when you `ssh` later.

  ```txt
  Host *.<DOMAIN_NAME>                          # <- i.e: "Host *.example.com"
        StrictHostKeyChecking=accept-new        # Don't have to say `yes` first time connecting
        CheckHostIP no                          # IP Changes all the time
        UserKnownHostsFile=/dev/null            # Keep quiet that IP is changing
        User=ec2-user                           # Default AWS User
        IdentityFile=~/.ssh/container-manager   # The Key we just setup
  ```

  The `*.` before `<DOMAIN_NAME>` will match any sub-domain/container you spin up.

- SSH into the instance:

  ```bash
  # If ~/.ssh/config is setup:
  ssh <CONTAINER_ID>.<DOMAIN_NAME>
  ```

- If using FileZilla:

  - To add the private key, go to `Edit -> Settings -> Connection -> SFTP` and add the key file there.
  - For the URl, put `sftp://<GAME_URL>`. The username is `ec2-user`. Password is blank. Port is 22.
  - Files are stored in `/mnt/efs/<Volumes>`.
