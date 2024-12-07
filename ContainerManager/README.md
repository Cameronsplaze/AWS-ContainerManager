# Container Manager

This is designed so you only need one base stack that you deploy first, then you can deploy any number of leaf stacks on it. This lets you modify one leaf/container stack, without affecting the rest, and still have shared resources to reduce cost/complexity where appropriate.

- The [./leaf_stack](./leaf_stack/README.md) is what runs a single container. One `leaf_stack` for one container.
- The [base_stack.py](./base_stack.py) is common architecture that different containers can share (i.e VPC). Multiple "Leaf Stacks" can point to the same "Base Stack".
- The [./utils](./utils/README.md) are functions that don't fit in the other two. Mainly config readers/parsers.

Click here to jump to '[Base Stack Config Options](#base-stack-config-options)'. It's the last section, since it's the longest.

## Leaf Stack Summary

![picture](/Resources/AWS-ContainerManager_Basic_Diagram.png)
<!-- Original board: https://sketchboard.me/REucJJtlrBCi#/ -->

**Not an all inclusive diagram**: There's more not shown, like EFS mounted to both the EC2 Task and ASG Instance, SNS Alerts, etc.

The system is designed all around the Auto Scaling Group (ASG). This way, if the ASG spins up in any way (DNS query comes in, or you change the desired_count in the console), everything spins up around it. If a alarm triggers, it just has to spin the ASG back down and everything will naturally follow suit.

See the [leaf_stack README.md](./leaf_stack/README.md) for more info.

## Base Stack Summary

The [base stack](./base_stack.py) is the common architecture that different containers can share. Most notably:

- **VPC**: The overall network for all the containers and EFS. We used a public VPC, because private cost ~$32/month per subnet (because of the NAT). WITH ec2 costs, I want to shoot for about than $100/year with solid usage.
- **SSH Key Pair**: The key pair to SSH into the EC2 instances. Keeping it here lets you get into all the leaf_stacks without having to log into AWS each time you deploy a new leaf. If you destroy and re-build the leaf, this keeps the key consistent too.
- **SNS Notify Logic**: Designed for things admin would care about. This tells you whenever the instance spins up or down, if it runs into errors, etc.
- **Route53**: The base domain name for all stacks to build from.

## Base Stack Config Options

These are config options for when you deploy the base stack, to fine-tune it to your needs. Update the [base-stack-config.yaml](/base-stack-config.yaml) file in the root of this repo.

---

### `Vpc`

- (`dict`, **Required**): Config options for the VPC.

### `Vpc.MaxAZs`

- (`int`, Default: `1`): The number of AZ's (Availability Zones) to use in the VPC. Two means high-availability, BUT your EFS storage costs will double.

   ```yaml
   Vpc:
     MaxAZs: 1
   ```

### `Domain`

- (`dict`, **Required**): Config options for the domain.

### `Domain.Name`

- (`str`, **Required**): The root domain name for all the leaf_stack's.

   ```yaml
   Domain:
     Name: example.com
   ```

### `Domain.HostedZoneId`

- (`str`, Optional - kinda): The Route53 Hosted Zone ID for the domain of the domain name above. If not provided, it will be created. (Though you'll probably have to manually update the NS records in your registrar or something. I haven't tested this path yet. If you [buy a AWS Domain](https://aws.amazon.com/getting-started/hands-on/get-a-domain/), it'll come with a HostedZoneID anyways).

   ```yaml
   Domain:
     HostedZoneId: Z1234567890
   ```

### `AlertSubscription`

- (`list`, Optional): Any number of key-value pairs, where the key is the protocol (i.e "Email"), and the value is the endpoint (i.e `DoesNotExist@gmail.com`)

   ```yaml
   AlertSubscription:
     - Email: DoesNotExist1@gmail.com
     - Email: DoesNotExist2@gmail.com
   ```

   This is to get notified for ANY leaf stack events. Intended for admin to keep an eye on everything without having to subscribe to every [leaf stack config's AlertSubscription](/Examples/README.md#alertsubscription)

   Options like `SMS` and `HTTPS` I hope to add [at some point](https://github.com/Cameronsplaze/AWS-ContainerManager/issues/22), but `Email` was the easiest to just get off the ground.

   Only have someone subscribed to this, **OR** the leaf stack, **NOT BOTH**. Otherwise you'll get an alert from each one any time something happens.

---
