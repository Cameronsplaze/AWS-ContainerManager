# AWS Container Manager

Run Minecraft, Valheim, or any container in AWS!

This CDK project spins up the container when someone connects, then spins it back *down* when they're done automatically! It's a great way to save money on your game/container servers, without opening your home network to the world.

---

## Quick Start

### First time setup

First install [aws_cdk](https://docs.aws.amazon.com/cdk/v2/guide/getting_started.html).

Once you have `python3` and `npm` installed, run `make update` to get everything to the latest version. (As dependabot upgrades stuff, you'll want to run this to stay up-to-date once in a while too).

- If it complains about NPM not being ran with root, follow [this stackoverflow guide](https://stackoverflow.com/a/55274930) to let non-sudo work.

```bash
# Setup the venv
python3 -m venv .venv
source .venv/bin/activate
# update all npm and python packages
make update
# Setup the env vars
cp vars.env.example vars.env
nano vars.env # Use the text editor that's better than vim >:)
```

### Deploy the Stack

There's two stacks, the 'base' stack and the 'leaf' stack. Multiple leaf stacks can/should use the **same** base stack. Deploy the base stack first, but you shouldn't have to again unless you change something in it.

#### Base Stack

The config options for the stack are in [./base-stack-config.yaml](./base-stack-config.yaml). Info on each option is in [./ContainerManager/README.md](./ContainerManager/README.md#editing-the-base-stack-config).

If you need a `HostedZoneId`, you can [buy a domain from AWS](https://aws.amazon.com/getting-started/hands-on/get-a-domain/).

```bash
# IF a new shell
source .venv/bin/activate
source vars.env
# Actually deploy:
make cdk-deploy-base
```

#### Leaf Stack

The config examples are in `./Examples/*-example.yaml`. Info on each config option and writing your own config is in [./Examples/README.md](./Examples/README.md). For a quickstart, just run:

```bash
# IF a new shell
source .venv/bin/activate
source vars.env
# Edit the config to what you want:
cp ./Examples/Minecraft-example.yaml ./Minecraft.yaml
nano ./Minecraft.yaml
# Actually deploy:
make cdk-deploy-leaf config-file=./Minecraft.yaml
```

### Connecting to the Container

Now your game should be live at `<FileName>.<DOMAIN_NAME>`! (So `minecraft.<DOMAIN_NAME>` in this case. No ".yaml"). This means one file per stack. If you want to override this, see the [Different Maturities](#different-maturities) section below.

> [!NOTE]
> It takes ~2 minutes for the game to spin up when it sees the first DNS connection come in. Just spam refresh.

If it's downloading updates, keep spamming refresh. It sees those connection attempts and resets the time before spinning down.

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

## Running Commands on the Host / Accessing Files

### SSM Session Manager

Core AWS docs for this are [here](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-getting-started-enable-ssh-connections.html#ssh-connections-enable).

(I can't get it automated. Use the SSH method below for now. Details are [here](https://github.com/Cameronsplaze/AWS-ContainerManager/issues/2) if you're interested!).

### SSH into the Host

The files are mounted to `/mnt/efs/<Volumes>` on the HOST of the container, to give easy access to modify them with SFTP.

To connect to the container:

1) Get SSH private key from AWS System Manager (SSM) Param Storage

    If you have more than one key: Go to `EC2` => `Network & Security` => `Key Pairs`. Look for `ContainerManager-BaseStack-SshKey`, and copy it's `ID`. Now go to `SSM` => `Parameter Store`, and select the key that matches `/ec2/keypair/<ID>`. (I've tried adding tags/descriptions to the SSM key to skip the first step, they don't go through.)

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

### Moving files from Old EFS to New

If you have an existing EFS left over from deleting a stack, there's no way to tell the new stack to "just use it". You have to transfer the files over.

- **Using SFTP**: The easiest, but most expensive since the files leave AWS, then come back in. Follow the [ssh guide](#ssh-into-the-host) to setup a SFTP application.
- **Using DataSync**: Probably the cheapest, but I haven't figured it out yet. If you do this a-lot, it's worth looking into.

---

## Docs and Extra Info

How the docs work in this project, is each directory has a `README.md` that explains what's in that directory. The farther you get down a path, the more detailed the info gets. This `README.md` in the root of the project is a high-level overview of the project.

### AWS Architecture

See [./ContainerManager/README.md](./ContainerManager/README.md#how-the-stack-works) for a overview of the architecture.

Or [./ContainerManager/leaf_stack/README.md](./ContainerManager/leaf_stack/README.md#high-level-architecture) for a aws architecture diagram of the core/leaf stack.

---

## Devel Stuff

If you're looking for *why* I made some decisions over others, check out the [DESIGN.md](./DESIGN.md) file.

### Development Tricks

Pylint is baked into the makefile, just use this to lint everything:

```bash
make pylint
```

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

### Different Maturities

There's currently two maturities you can set, `devel` and `prod` (prod being the default). `devel` has defaults for developing (i.e removes any storage with it when deleted). It also keeps the containers you're testing with, separate from any games you're activity running. For example, you can:

```bash
# Create the devel base stack:
make cdk-deploy-base maturity=devel
# Add an application to it:
make cdk-deploy-leaf maturity=devel config-file=<FILE>
# Delete said leaf stack
make cdk-destroy-leaf maturity=devel config-file=<FILE>
# And never touch the stuff in the normal stacks!
```

> [!WARNING]
> The `container-id` has to be unique per ACCOUNT. To help with this, you can use the cli flag to override it to something else if the other maturity-stack is already using it. (By default, `container-id` is the filename of the config without the extension).

For example, you can have GH Actions deploy to prod, but use devel locally. Both can still be in the same AWS account:

```bash
# To deploy to prod, it'll look like:
#    (You can have `maturity=prod` if you want, but it's the default).
make cdk-deploy-leaf config-file=./Examples/Minecraft-example.yaml container-id=Minecraft
# And then manually deploying to devel could look like:
make cdk-deploy-leaf config-file=./Examples/Minecraft-example.yaml maturity=devel
```

This would still give you two stacks, each with a different base stack. They won't conflict since the first command got overridden to `minecraft`, and the second one is using the default `minecraft-example` from the filename:

- `minecraft.<DOMAIN>`: On the normal prod stack.
- `minecraft-example.<DOMAIN>`: In the devel stack.

> [!NOTE]
> If you want to update an existing stack, you MUST pass in the same exact flags you deployed with! Otherwise it's going to try to create a new stack entirely.
