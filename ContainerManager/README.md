# Container Manager

This is designed so you only need one base stack that you deploy first, then you can deploy any number of "leaf stack groups" on it. (A single leaf-stack-group is for managing a single container). This lets you modify one leaf-stack-group, without affecting the rest, and still have shared resources to reduce cost/complexity where appropriate.

- The [./leaf_stack_group](./leaf_stack_group/README.md) is what runs a single container. One `leaf_stack_group` for one container. It contains **three** stacks in the group.
- The [./base_stack](./base_stack/README.md) is common architecture that different containers can share (i.e VPC, imported HostedZone, ssh key). Multiple "Leaf Stack Groups" can point to the same "Base Stack".
- The [./utils](./utils/README.md) are functions that don't fit in the other two. Mainly config readers/parsers.

Click here to jump to '[Base Stack Config Options](#base-stack-config-options)'. It's the last section, since it's the longest.

## Leaf Stack Group Summary

![picture](../Resources/AWS-ContainerManager_Basic_Diagram.png)
<!-- Original board: https://sketchboard.me/REucJJtlrBCi#/ -->

**Not an all inclusive diagram**: There's more not shown, like EFS mounted to both the EC2 Task and ASG Instance, SNS Alerts, etc.

The system is designed all around the Auto Scaling Group (ASG). This way, if the ASG spins up in any way (DNS query comes in, or you change the desired_count in the console), everything spins up around it. If a alarm triggers, it just has to spin the ASG back down and everything will naturally follow suit.

See the [leaf_stack_group's README.md](./leaf_stack_group/README.md) for more info.

## Base Stack Summary

The [base stack](./base_stack/README.md) is a shared resources stack to help keep running multiple containers cheap. By also keeping things like an SSH key here, you don't have to juggle multiple keys for every container you want to run. (Or add your email for alerts on every container stack too).

Anything that can be here instead of the leaf stacks, should be.

## Base Stack Config Options

These are config options for when you deploy the base stack, to fine-tune it to your needs. Update the [base-stack-config.yaml](../base-stack-config.yaml) file in the root of this repo.

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

- (`str`, **Required**): The Route53 Hosted Zone ID for the domain of the domain name above. If you [buy a AWS Domain](https://aws.amazon.com/getting-started/hands-on/get-a-domain/), put it's HostedZoneId here. (Required because whatever path you take to get a domain, you'll need to create a Hosted Zone for it anyways).

   ```yaml
   Domain:
     HostedZoneId: Z1234567890
   ```

### `AlertSubscription`

- (`dict`, Optional): Any number of key-value pairs, where the key is the protocol (i.e "Email"), and the value is a space separated list (i.e `Does@Not.Exist Does@Not.Exist2`)

   ```yaml
   AlertSubscription:
     Email: |
       DoesNotExist1@gmail.com
       DoesNotExist2@gmail.com
   ```

   This is to get notified for ANY leaf stack events. Intended for admin to keep an eye on everything without having to subscribe to every [leaf stack config's AlertSubscription](../Examples/README.md#alertsubscription)

   Options like `SMS` and `HTTPS` I hope to add [at some point](https://github.com/Cameronsplaze/AWS-ContainerManager/issues/22), but `Email` was the easiest to just get off the ground.

   Only have someone subscribed to this, **OR** the leaf stack, **NOT BOTH**. Otherwise you'll get an alert from each one any time something happens.

   (It's setup like this, so a single GitHub Secret can pass in any number of emails)

---
