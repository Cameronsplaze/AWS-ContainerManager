# AWS Container Manager

Run Minecraft, Valheim, or any container automatically in AWS!

This CDK project spins up the container when someone connects, then spins it back *down* when they're done automatically! It's a great way to host game/container servers for your friends cheaply, **without opening your home network to the outside world.**

---

## Quick Start

### First Time Setup - Configure AWS

- First install [aws_cdk](https://docs.aws.amazon.com/cdk/v2/guide/getting_started.html).
- Setup your [./aws/credentials](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html) file, along with the region you want to deploy to.
- Run `make cdk-bootstrap` to [bootstrap cdk to your account](https://docs.aws.amazon.com/cdk/v2/guide/bootstrapping.html), in both the region from the last step, and `us-east-1` ([required for Route53](TODO LINK THIS WHEN IT EXISTS)).

### First Time Setup - This Project

- Make sure `python3` and `npm` are installed in your system.
- Setup a python environment with:

  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

- Update/Install everything with `make update`.
  - Note: If it complains about NPM not being ran with root, follow [this stackoverflow guide](https://stackoverflow.com/a/55274930) to let non-sudo work. (I couldn't get the `~/.profile` line working with vscode, so I added it to `~/.bashrc` instead).

> [!NOTE]
> Now that you have it setup, you'll only have to do `source .venv/bin/activate` on new shells from here on out. (And `make update` once in a while to get the latest packages).

### Deploying the App (Manually)

There's two stacks, the 'base' stack and the 'leaf' stack. Multiple leaf stacks can/***should*** use the *same* base stack to save costs. Deploy the base stack first, but you shouldn't have to again unless you change something in it.

First setup your Environment Variables used for deploying, and just delete any sections you're not using:

```bash
source .venv/bin/activate
cp vars.env.example vars.env
nano vars.env # Use the text editor that's better than vim :)
source vars.env # Do this after every edit you make too!
```

**For more Advanced Customization while Deploying**, see [Advanced Deployments](TODO LINK THIS WHEN IT EXISTS).

#### Base Stack

The config options for the stack are in [./base-stack-config.yaml](/base-stack-config.yaml). Info on each option is in [./ContainerManager/README.md](./ContainerManager/README.md#editing-the-base-stack-config).

If you need a `HostedZoneId`, you can [buy a domain from AWS](https://aws.amazon.com/getting-started/hands-on/get-a-domain/), then copy the Id from the console. (AWS won't let you automate this step).

```bash
make cdk-deploy-base
```

#### Leaf Stack

The config examples are in `./Examples/*.example.yaml`. Info on each config option and writing your own config is in [./Examples/README.md](/Examples/README.md#config-file-options).

For a QuickStart example, if you're running Minecraft, just run:

```bash
# Edit the config to what you want:
cp ./Examples/Minecraft.java.example.yaml ./Minecraft.yaml
nano ./Minecraft.yaml
# Actually deploy:
make cdk-deploy-leaf config-file=./Minecraft.yaml
```

### Connecting to the Container

Now your game should be live at `<FileName>.<DOMAIN_NAME>`! (So `minecraft.<DOMAIN_NAME>` in this case. No ".yaml"). This means one file per stack. If you want to override this, see the [Deploy / Destroy](TODO LINK THIS WHEN IT EXISTS) section below.

> [!NOTE]
> It takes ~2-4 minutes for the game to spin up when it sees the first DNS connection come in. Just spam refresh.

If it's installing updates, keep spamming refresh. It sees those connection attempts, and resets the watchdog threshold (time before spinning down).

### Cleanup / Destroying the Stacks

You have to clean up all the leaf stacks first, then the base stack.

If your config has [Volume.RemovalPolicy](TODO LINK THIS WHEN IT EXISTS) set to `RETAIN` (the default), it'll keep the server files inside AWS but still remove the stack.

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

> [!NOTE]
> There likely won't be enough traffic from JUST ssh to stop the container from spinning down. Just connect to the container with whatever client it needs (Minecraft, Valheim, etc) to keep it up.

The files are mounted to `/mnt/efs/<Volumes>` on the HOST of the container, to give easy access to modify them with SFTP/SSH/etc.

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

## Writing your own Config

The config examples are in `./Examples/*.example.yaml`. Info on each config option and writing your own config is in [./Examples/README.md](/Examples/README.md#config-file-options).

### If the container is unexpectedly Going Down, or Staying Up

There's a few alarms inside the app that are supposed to shut down the system when specific events happen. Check the [Dashboard](https://console.aws.amazon.com/cloudwatch/home#dashboards) to see which alarm is (or isn't) triggering. (If you [disabled the dashboard](/Examples/README.md#dashboardenabled), view the [Alarms in CloudWatch](https://console.aws.amazon.com/cloudwatch/home#alarmsV2:)).

- If the `Container Activity` alarm is the problem, adjust the [Watchdog.Threshold](/Examples/README.md#watchdogthreshold) config key.
- If the `Instance Left Up` alarm is triggered, adjust the [whatever](/Examples/README.md#watchdoginstanceleftup) config keys.
- If the `Break Crash Loop` alarm is triggered, the container either crashed or is refusing to start. View the container in the console to see what's going on. (Select your cluster from [ECS Clusters](https://console.aws.amazon.com/ecs/v2/clusters) -> `*/* Tasks running`. Debug info is likely in either `Logs` or `Events`, depending what is causing this).

## Cost of Everything

- TODO: [Create Cost Estimate](https://calculator.aws/#/) (It's not much).
- Buying a domain from AWS is an extra `$3/year` for the cheapest I could find (`Register domains` -> `Standard pricing` -> `Price` to sort by price).
- The [EC2 Costs](https://aws.amazon.com/ec2/pricing/on-demand/) aren't included because they're the highest factor. You're only charged while people are actively online, but the bigger instances are also more pricey.

## Makefile Commands

### (cdk) Synth / Deploy / Destroy

These are the core commands of cdk. Both deploy and destroy are broken into two for the base and leaf stacks. So in total, you have: `cdk-synth`, `cdk-deploy-base`, `cdk-deploy-leaf`, `cdk-destroy-base`, `cdk-destroy-leaf`.

**With the exception of** the `*-base` commands, the other three commands have three parameters for customization:

> ![NOTE]
> When deploying/destroying a stack, all three parameters must be exactly the same as the first deployment.
>
> If you change *one* and deploy again, you'll create a new stack. If the `cdk-destroy-leaf` command doesn't have the same params as the `cdk-deploy-leaf` did, it won't be able to find a stack to delete.

#### config-file

This controls which "leaf stack" you're working on. It's a path to the config yaml.

Optional for `cdk-synth`:

```bash
# Just lint the base stack:
make cdk-synth
# Lint the base stack, and a leaf stack with a config:
make cdk-synth config-file=./Examples/<MyConfig>.yaml
```

**Required** for both `*-leaf` commands:

```bash
make cdk-deploy-leaf config-file=./Examples/Minecraft.java.example.yaml
# Domain will be: `minecraft.java.example.<YOUR_DOMAIN>`
```

#### container-id

Optional for all three commands. This fixes two issues:

- The `container-id` has to be unique per **aws account**. If you want to deploy two of the same yaml to your account, at least one will need to set this.
- This overrides the domain prefix. If you want a descriptive yaml name, but small domain name, use this.

```bash
make cdk-deploy-leaf config-file=./Examples/Minecraft.java.example.yaml container-id=minecraft
# Domain will be: `minecraft.<YOUR_DOMAIN>`
```

#### maturity

There's currently two maturities you can set, `devel` and `prod` (prod being the default). `devel` has defaults for developing (i.e removes any storage with it when deleted). It also keeps the containers you're testing with, separate from any games you're activity running.

```bash
# Create the devel base stack:
make cdk-deploy-base maturity=devel
# Add an application to it:
make cdk-deploy-leaf maturity=devel config-file=<FILE>
# Delete said leaf stack
make cdk-destroy-leaf maturity=devel config-file=<FILE>
# And never touch the stuff in the normal stacks!
```

### pylint

Lints all python files. Useful when developing.

```bash
make pylint
```

### aws-whoami

Prints your current user arn, including account id. Useful for checking if aws-cli is setup correctly, and if you're using the right aws account before deploying.

### update

Updates both `npm` and `python pip` packages.

```bash
make update
```

### cdk-bootstrap

For setting up cdk into your AWS Account. See the [AWS QuickStart](#first-time-setup---configure-aws) section for more details.

## Automatic Deployments with GitHub Actions

To automatically deploy your stack with the lastest cdk changes as they come out, see the [workflows docs](/.github/workflows/README.md).

## Learning or Developing on the Architecture

See [./ContainerManager/README.md](TODO LINK THIS WHEN IT EXISTS) for diagrams and an overview of the app's architecture.

### Docs and Extra Info

In each directory has a `README.md` that explains what's in that directory. The farther you get down a path, the more detailed the info gets. This `README.md` in the root of the project is a high-level overview of the project.

### Develop with Multiple Maturities

I made a [maturity key](#maturity) when deploying to specifically help developers. There's a few other nice commands in [the Makefile](#makefile-commands) too to help out!

### Design Choices of the Project

If you're looking for *why* I made some decisions over others, check out the [DESIGN_CHOICES.md](./DESIGN_CHOICES.md) file. If it's not there, feel free to open an Issue or Discussion! I'm always looking for ways to improve this project, no matter how minor.
