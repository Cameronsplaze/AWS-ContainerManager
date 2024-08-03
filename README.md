# AWS Container Manager

Run Minecraft, Valheim, or any container in AWS!

This CDK project spins up the container when someone connects, then spins it back *down* when they're done automatically! It's a great way to save money on your game/container servers, without opening your home network to the world.

---

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

#### Base Stack

The config options for the stack are in [./base-stack-config.yaml](./base-stack-config.yaml). Info on each option is in [./ContainerManager/README.md](./ContainerManager/README.md#editing-the-base-stack-config).

If you need a `HostedZoneId`, you can [buy a domain from AWS](https://aws.amazon.com/getting-started/hands-on/get-a-domain/).

For a quickstart, just run:

```bash
# `source` if new shell
source .venv/bin/activate
source vars.env
# Actually deploy:
make cdk-deploy-base
```

#### Leaf Stack

The config examples are in `./Examples/*-example.yaml`. Info on each config option and writing your own config is in [./Examples/README.md](./Examples/README.md). For a quickstart, just run:

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

Now your game should be live at `<FileName>.<DOMAIN_NAME>`! (So `minecraft.<DOMAIN_NAME>` in this case. No ".yaml")

> [!NOTE]
> It takes ~2 minutes for the game to spin up when it sees the first DNS connection come in. Just spam refresh.

### Cleanup / Destroying the Stacks

You have to clean up all the leaf stacks first, then the base stack.

If your config has `Volume.RemovalPolicy` set to `RETAIN`, it'll keep your data inside AWS but still remove the stack.

```bash
# Destroying one leaf:
make cdk-destroy-leaf config-file=./Minecraft.yaml
# Destroying the base stack
make cdk-destroy-base
```

---

## Docs and Extra Info

How the docs work in this project, is each directory has a `README.md` that explains what's in that directory. The farther you get down a path, the more detailed the info gets. This `README.md` in the root of the project is a high-level overview of the project.

### AWS Architecture

See [./ContainerManager/README.md](./ContainerManager/README.md#how-the-stack-works) for a overview of the architecture.

Or [./ContainerManager/leaf_stack/README.md](./ContainerManager/leaf_stack/README.md#high-level-architecture) for a aws architecture diagram of the core/leaf stack.

---

## Running Commands on the Host / Accessing Files

### SSM Session Manager

Core AWS docs for this are [here](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-getting-started-enable-ssh-connections.html#ssh-connections-enable).

(I can't get it automated. Use the SSH method below for now. Details are [here](https://github.com/Cameronsplaze/AWS-ContainerManager/issues/2) if you're interested!).

### SSH into the Host

The files are mounted to `/mnt/efs/<Volumes>` on the HOST of the container, to give easy access to modify them with SFTP.

To connect to the container:

1) Get SSH private key from AWS System Manager (SSM) Param Storage
2) Add it to agent:

    ```bash
    nano ~/.ssh/container-manager # Paste the key from SSM
    chmod 600 ~/.ssh/container-manager
    ssh-add ~/.ssh/container-manager
    ```

3) Add this to your `~/.ssh/config`:

    **NOTE**: The DOMAIN_NAME must be all lowercase! Otherwise it won't be case-insensitive when you `ssh` later.

    ```txt
    Host *.<DOMAIN_NAME>                          # <- i.e: "Host *.example.com"
          StrictHostKeyChecking=accept-new        # Don't have to say `yes` first time connecting
          CheckHostIP no                          # IP Changes on every startup
          UserKnownHostsFile=/dev/null            # Keep quiet that IP is changing
          User=ec2-user                           # Default AWS User
          IdentityFile=~/.ssh/container-manager   # The Key we just setup
    ```

4) Access the host!

   - `ssh` into the instance:

      ```bash
      ssh <CONTAINER_ID>.<DOMAIN_NAME>
      ```

      And now you can use [docker](https://docs.docker.com/reference/cli/docker/container/exec/) commands if you need to jump into the container! Or view the files with

      ```bash
      ls -halt /mnt/efs
      ```

   - Use `FileZilla` to add/backup files:
      - To add the private key, go to `Edit -> Settings -> Connection -> SFTP` and add the key file there.
      - For the URl, put `sftp://<GAME_URL>`. The username is `ec2-user`. Password is blank. Port is 22.

---

## Devel Stuff

If you make changes, and would like to `cdk synth`, there are `make` commands to help. Use:

```bash
# Just lint the base stack:
make cdk-synth
# Lint the base stack, and a leaf stack with a config:
make cdk-synth config-file=./Examples/<MyConfig>.yaml
```

You can also quickly check which aws account you're configured to use, before you accidentally deploy to the wrong account:

```bash
make aws-whoami
```















---

**Don't read past this, still re-writing everything after.**

---

## TODO (In order (not really...))

### Phase 1, MVP

- DONE!

### Phase 2, Optimize and Cleanup

- DONE!

### Phase 3, Get ready for Production!

- Go through Console and see if everything looks like you want. Check for warnings.

- Write up guide on moving files into EFS if a stack already existed
  - Check if you can import EFS into the stack, I don't think you can.
  - Check Data Sync, it keeps you in network. (Move from the previous stacks EFS into the new stack)
  - Just use SFTP with Filezilla or something. Most expensive but easiest.

### Phase 4, Add tests

- Using pytest. Will also expand this to get timings of how long each part of the stack takes to spin up/down when someone connects.
  - [cdk-nag](https://github.com/cdklabs/cdk-nag) can flag some stuff

### Continue after this

I'm moving longer-term ideas to [DESIGN.md](./DESIGN.md). This section is focused on getting the MVP up and running.

---
