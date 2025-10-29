# Creating or Modifying Config Files

These are config options when you deploy, for a single leaf. (The file's name becomes the sub-domain for the stack, so one file for one stack. I.e `Minecraft.java.example.yaml` -> `minecraft.java.example.my-domain.com`). See any `*.example.yaml` in this directory for examples. (If you need to override the domain name to something new when deploying, use the `container_id=` key. See the [CDK Deploy Command](../README.md#container-id) section for more details.)

The code that actually parses these options is in [config_loader.py](../ContainerManager/utils/config_loader.py).

Click here to jump to '[Config File Options](#config-file-options)'. It's the last section, since it's the longest.

## Gotchas when Writing Configs

- [Environment Variables](#containerenvironment) to set **for the container itself** when Writing Configs:
  - **For backups**: Completely Disable. We use EFS behind the scenes. Use the [Volumes.EnableBackups](#volumesidenablebackups) option if you want backups. **IF you do it inside the container**, you'll be doing backups of backups, and pay a lot more for storage. Plus if your container gets hacked, they'll have access to the backups too.
  - **For updating the server**: Since the container is only up when someone is connected, any "idle update" strategy won't work. The container has to check for updates when it **first** spins up. Also disable so that it doesn't conflict with the [Watchdog.Threshold](#watchdogthreshold) and keep the container up.
  - **For file permissions (UID/GID)**: Set to `1000:1000`. When you access the files through the EC2, this'll make them a LOT easier to modify/upload to.
- **Whitelist users inside of the Configs**: All the containers I've tested so far provide some form of whitelist. You can use it, but it means you have to re-deploy this project every time you add someone. It takes forever, and (might?) kick everyone for a bit. If you can, use the game's built-in whitelist feature instead. (Unless maybe you don't expect it changing often, like with an admin list.)

## Adding a new Example Config to the Repo

1) Ask if it's a game I'll want to support, either by [Issues](https://github.com/Cameronsplaze/AWS-ContainerManager/issues) or [Discussions](https://github.com/Cameronsplaze/AWS-ContainerManager/discussions/categories/q-a). (Even if I don't add it here, I might still help you add it to your fork)
2) Create a new file in this [./Examples](./) directory. Make sure it ends with `*.example.yaml`.
3) Make sure it correctly Synths. (If you're doing a PR, it'll happen automatically)
4) Once it Synths, add it to the "Settings -> Branches -> `main` -> Required Status Checks" list. (If you don't have permissions, remind me to inside the PR please).

## Config File Options

You can also look at the yaml's in the [./Examples](./) directory here to see how each of these are used directly.

The options for the base stack are in [/ContainerManager/README.md](../ContainerManager/README.md#base-stack-config-options).

---

### `Ec2`

- (`dict`, **Required**): Config options for anything Ec2 related.

### `Ec2.InstanceType`

- (`str`, **Required**): The EC2 instance type to use. I.e `r4.large`, `m5.large`, etc. This config option will verify it's a valid EC2 instance type, then replace this block with the [`EC2.Client.describe_instance_types`](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2/client/describe_instance_types.html#EC2.Client.describe_instance_types) response. (For example, `Ec2.MemoryInfo.SizeInMiB` will become a valid lookup in the stack).

  The ec2 instance must have at least 2 GB of memory, so that the host and guest can both run. **1 GB is reserved for the host**.

   ```yaml
   Ec2:
     InstanceType: m5.large
   ```

---

### `Container`

- (`dict`, **Required**): Config options for anything Container related.

### `Container.Image`

- (`str`, **Required**): The Docker image to use. I.e `itzg/minecraft-server`, `lloesche/valheim-server`, etc.

   ```yaml
   Container:
     Image: itzg/minecraft-server
   ```

### `Container.Ports`

- (`list`, **Required**): The list of ports to expose, in the form of `Type: number`. I.e:

   ```yaml
   Container:
     Ports:
       - TCP: 25565
       - UDP: 1234
       # ...
   ```

### `Container.Environment`

- (`dict`, Optional): The environment variables to pass into the container, as key-value pairs.

   ```yaml
   Container:
     Environment:
       EULA: True
       TYPE: "PAPER"
      # ...
   ```

---

### `Volumes`

- (`dict`, Optional): Config options for Volumes (Persistent Storage).

   Each "block" defines one volume, for example:

   ```yaml
   Volumes:
     ## Minimal Volume:
     # EnableBackups, and KeepOnDelete are True by default
     Data: # <- The Id of the volume
       Paths:
         - Path: /data
     ## Or if you wanted something persistent, but not backed up:
     #     (i.e the path to the valheim server binary. Saves
     #      on startup time, but not critical if lost.)
     DownloadCache: # <- The Id of the volume
       EnableBackups: False
       KeepOnDelete: False
       Paths:
         - Path: /opt/valheim
   ```

> [!NOTE]
> The filesystems inside `/mnt/efs` are labeled `Efs-<Id>` (I.e `Efs-Data` above). The Id **MUST** be unique in the config file. If you change it's Id after deploying, CDK will create a new EFS and you'll have to transfer data over manually (assuming KeepOnDelete is enabled. Otherwise the data is lost).

### `Volumes.<Id>.Type`

- (`str`, Optional, default=`EFS`): The type of volume to use. Currently only `EFS` is supported.

   I plan to add [`S3` support](https://github.com/Cameronsplaze/AWS-ContainerManager/issues/10) when I get a chance, this is here for future-proofing.

### `Volumes.<Id>.EnableBackups`

- (`bool`, Optional, default=`if "maturity" == "prod"`): If you should enable backups for the volume. This will increase the cost of the volume, BUT you'll have backups. (Maturity defaults to `prod` if not set. See [more info here](../README.md#maturity)).

### `Volumes.<Id>.KeepOnDelete`

- (`bool`, Optional, default=`if "maturity" == "prod"`): If you should keep the data when the stack is destroyed. (Maturity defaults to `prod` if not set. See [more info here](../README.md#maturity)).

### `Volumes.<Id>.Paths`

- (`list`, **Required**): The list of paths to persist INSIDE the container.

   For example, if you **didn't** want to backup data directory in the [above example](#volumes), you could add it to the Server Binary's EFS:

   ```yaml
   Volumes:
     - EnableBackups: False
       KeepOnDelete: False
       Paths:
         - Path: /opt/valheim
         - Path: /data
   ```

### `Volumes.<Id>.Paths[*].Path`

- (`str`, **Required**): The path inside the container to persist. I.e `/data`, `/opt/valheim`, `/config`, etc.

### `Volumes.<Id>.Paths[*].ReadOnly`

- (`bool`, Optional, default=`False`): If the path should be read-only.

   ```yaml
   Volumes:
     - Paths:
        - Path: /config
          ReadOnly: True
   ```

---

### `Watchdog`

- (`dict`, **Required**): Config options for how long to wait before shutting down, and what is considered to be "idle".

### `Watchdog.Threshold`

- (`int`, **Required**): Bytes per Second. If there's less than this for `MinutesWithoutConnections` long, the container will spin down.

   **To find this number**: just set it to `20` to deploy the stack. Then go into the `ContainerManager-<container-id>-Dashboard` and check the `Alarm: Container Activity` Graph. This is low, so it won't ever spin down. **DON'T** connect, just watch the graph for ~15 minutes and see what it peaks at. Set this value to just above that.

   If you're having problems with the container spinning down too quickly, you'll have to lower this number. If it's staying up too long, you'll have to raise it.

   I couldn't make this have a default, because it's too different for each game. If I default it to 20, there's a risk of people not reading docs, and having a instance left up 24/7.

### `Watchdog.MinutesWithoutConnections`

- (`int`, Optional, default=`7`): How many minutes below the [threshold](#watchdogthreshold) before shutting down.

   ```yaml
   Watchdog:
     # If you don't get more than 900 bytes per second for 10 minutes, shut down:
     Threshold: 900
     MinutesWithoutConnections: 10
   ```

### `Watchdog.InstanceLeftUp`

- (`dict`, Optional): Config options for what to do if the instance is left up for a long time.

   ```yaml
   Watchdog:
     InstanceLeftUp:
       # If the instance has been up for 12 hours, alert the admin:
       DurationHours: 12 # Default=8
       # And shut it down:
       ShouldStop: True # Default=False
   ```

### `Watchdog.InstanceLeftUp.DurationHours`

- (`int`, Optional, default=`8`): How many hours before alarming the instance has been running this long. ALL alerts happen through [AlertSubscription](#alertsubscription).

### `Watchdog.InstanceLeftUp.ShouldStop`

- (`bool`, Optional, default=`False`): When [DurationHours](#watchdoginstanceleftupdurationhours) is reached: Should the container stop?

---

### `AlertSubscription`

- (`dict`, Optional): Any number of key-value pairs, where the key is the protocol (i.e "Email"), and the value is a space separated list (i.e `Does@Not.Exist Does@Not.Exist2`)

   ```yaml
   AlertSubscription:
     Email: |
       DoesNotExist1@gmail.com
       DoesNotExist2@gmail.com
   ```

   Options like `SMS` and `HTTPS` I hope to add [at some point](https://github.com/Cameronsplaze/AWS-ContainerManager/issues/22), but `Email` was the easiest to just get off the ground.

   Adding subscriptions here instead of [the base stack config](../ContainerManager/README.md#alertsubscription), will only give you *some* of the events, and only specific to *this* stack. Mainly used for friends connecting to the game they love. Only have someone subscribed to this, **OR** the base stack, **NOT BOTH**.

   (It's setup like this, so a single GitHub Secret can pass in any number of emails)

---

### `Dashboard`

- (`dict`, Optional): Config options for the CloudWatch Dashboard.

   ```yaml
   Dashboard:
     # Look back an hour by default:
     IntervalMinutes: 60
     # If logs already have a timestamp in them:
     ShowContainerLogTimestamp: False
   ```

### `Dashboard.Enabled`

- (`bool`, Optional, default=`True`): If the dashboard should be enabled. You only get 3 free dashboards (per month?), so if you have a lot of stacks, you might want to disable this.

### `Dashboard.IntervalMinutes`

- (`int`, Optional, default=`30`): When you're viewing the dashboard, the default time to look back for all the graphs.

### `Dashboard.ShowContainerLogTimestamp`

- (`bool`, Optional, default=`True`): For the Container Log Widget, if you should show the timestamp field or not. (If the container log message already has them, you can disable this one then).

---
