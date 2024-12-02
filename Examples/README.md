# Writing your own Config Files

## Creating Configs

These are config options when you deploy, for a single leaf. (The file's name becomes the sub-domain for the stack, so one file for one stack. I.e `Minecraft.java.example.yaml` -> `minecraft.java.example.my-domain.com`). See any `*.example.yaml` in this directory for examples. (If you need to override the domain name to something new when deploying, use the `container_id=` key. See the developer section in the [root README.md](../README.md#different-maturities) for more details.)

If you're looking at automating updates to the deployments, or just deploying with GitHub, see the [GitHub Actions README](../.github/workflows/README.md).

### Config File Options

You can also look at the yaml's in the [./Examples](./) directory here to see how each of these are used directly.

- `Ec2`: (dict)

  - `InstanceType`: (Required, str)

    The EC2 instance type to use. I.e `t3.micro`, `m5.large`, etc.

- `Container`: (dict)

  - `Image`: (Required, str)

    The Docker image to use. I.e `itzg/minecraft-server`, `lloesche/valheim-server`, etc.
  
  - `Ports`: (Required, list)

    The list of ports to expose, in the form of `Type: number`. I.e:

    ```yaml
    Container:
      Ports:
        - TCP: 25565
        - UDP: 1234
        # ...
    ```

  - `Environment`: (Optional, dict)

    The environment variables to pass into the container, as key-value pairs.

    ```yaml
    Container:
      Environment:
        EULA: "TRUE"
        TYPE: "PAPER"
        # ...
    ```

- `Volumes`: (list)

  Each element is a config options `dict` for the volume.

  ```yaml
  Volumes:
    - Type: EFS # EFS or (eventually) S3. EFS is the default.
      Paths:
        - Path: /data
          ReadOnly: False
    # Or if you wanted something persistent, but not backed up:
    # (i.e the path to the valheim server binary. Saves
    #  on startup time, but not critical if lost.)
    - EnableBackups: False
      KeepOnDelete: False
      Paths:
        - Path: /opt/valheim
  ```

  For each element:

  - `KeepOnDelete`: (Optional, bool)

    If you should keep the data when the stack is destroyed. (Default=`True`)

  - `EnableBackups`: (Optional, bool)

    If you should enable backups for the volume. This will increase the cost of the volume, BUT you'll have backups. (Default=`True`)

  - `Paths`: (Optional, list)

    List of dicts of what to persist INSIDE the container. One single element of the list can have:

    - `Path`: (Required, str)

      The path inside the container to persist. I.e `/data`, `/config`, etc.

    - `ReadOnly`: (Optional, bool)
  
      If the path should be read-only. (Default=`False`).

    ```yaml
    Volumes:
      - Paths:
          - Path: /data
          - Path: /some/read/only/dir
            ReadOnly: True
    ```

- `Watchdog`: (dict)

  Config options for how long to wait before shutting down, and what is considered to be "idle".

  - `Threshold`: (Required, int)

    Bytes per Second. If there's less than this for `MinutesWithoutConnections` long, the container will spin down.

    To find this number, just set it to `20` to deploy the stack. Then go into the `ContainerManager-<container-id>-Dashboard` and check the `Alarm: Container Activity` Graph.

    I couldn't make this have a default, because it's too different for each game. If I set it to 20, there's a risk of people not reading docs, and having a instance be up 24/7.

  - `MinutesWithoutConnections`: (Optional, int)

    How many minutes without a connection before shutting down. (Default=`5`).

  - `InstanceLeftUp`: (dict)

    - `DurationHours`: (Optional, int)

      How many hours before alarming the instance has been running this long. ALL alerts happen through `AlertSubscription`. (Default=`8`).

    - `ShouldStop`: (Optional, bool)

      If `DurationHours` is reached, should it also stop the instance? (Default=`False`).

- `AlertSubscription`: (Optional, list)

  Any number of key-value pairs, where the key is the protocol (i.e "Email"), and the value is the endpoint (i.e "DoesNotExist@gmail.com")

    ```yaml
    AlertSubscription:
      - Email: DoesNotExist1@gmail.com
      - Email: DoesNotExist2@gmail.com
    ```

    Options like `SMS` and `HTTPS` I hope to add at some point, but `Email` was the easiest to just get off the ground.

    Adding it here instead of the base stack, will only give you *some* of the events, and only specific to *this* stack. Mainly used for friends connecting to the game they love. Only have someone subscribed to this, **OR** the base stack, **NOT BOTH**.

- TODO: Add dashboard section (specifically disable key, note that you only get 3 free dashboards at a time).

## Gotchas

- Container `Environment Variables` to set when Writing Configs:
  - **For backups**: Completely Disable. We use EFS behind the scenes. Use the `Volume.EnableBackups` if you want backups. **IF you do it inside the container**, you'll be doing backups of backups, and pay a lot more for storage. Plus if your container gets hacked, they'll have access to the backups too. Always use flags for the container to disable backups, and use EFS if you want them.
  - **For updating the server**: Since the container is only up when someone is connected, any "idle update" strategy won't work. The container has to check for updates when it first spins up.
- **Whitelist users inside of the Configs**: All the containers I've tested so far provide some form of this. You can use it, but it means you have to re-deploy this project every time you add someone. It takes forever, and (might?) kick everyone for a bit. If you can, use the game's built-in whitelist feature instead. (Unless maybe you don't expect it changing often, like with an admin list.)

## Adding a new Example to the Repo

1) Ask if it's a game I'll want to support, either by Issues or Discussions. (Even if I don't add it here, I might still help you add it to your fork)
2) Create a new file in this [./Examples](./) directory. Make sure it ends with `*.example.yaml`.
3) Make sure it correctly Synths. (If you're doing a PR, it'll happen automatically)
4) Once it Synths, add it to the "Settings -> Branches -> `main` -> Required Status Checks" list. (If you don't have permissions, remind me to inside the PR please).

And that's it!
