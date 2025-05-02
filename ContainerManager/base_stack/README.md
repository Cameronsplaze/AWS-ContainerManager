# Base Stack Summary

This is common architecture between leaf-stacks, combined to reduce costs and complexity.

## Base Stack ([./main.py](./main.py))

Deployed to the same region as you want to run the containers from.

- **VPC**: The overall network for all the containers and EFS. We used a public VPC, because private cost ~$32/month per subnet (because of the NAT). WITH ec2 costs, I want to shoot for less than $100/year with solid usage.
- **SSH Key Pair**: The key pair to SSH into the EC2 instances. Keeping it here lets you get into all the leaf_stacks without having to log into AWS each time you deploy a new leaf. If you destroy and re-build the leaf, this keeps the key consistent too.
- **SNS Notify Logic**: Designed for things admin would care about. This tells you whenever the instance spins up or down, if it runs into errors, etc.
- **Hosted Zone**: *Imports* a hosted zone into this stack. This way you only need one domain, and sub-domains are created off it. Each LeafStackGroup will still need to create their own HostedZone, because otherwise it can only hold a max of two sub-domains. (We use a log-group subscription filter to know when to spin up on a DNS hit, and you can only have two per log group. And you can only have one log group per HostedZone, which also has to exist BEFORE the HostedZone is created...).

# Why not have [domain_stack](../leaf_stack_group/domain_stack.py) as a second Base Stack?

This idea is theoretically great! By having the hosted-zone as a shared stack, and have the leaf stacks just add a dns record, you'd save `$0.50/month` per leaf stack. I tried it out [in this PR](https://github.com/Cameronsplaze/AWS-ContainerManager/pull/83). It had two problems.

- The major problem is you can only have two subscription filters on the hosted-zone's log group. Which means only two leaf-stacks per base-stack. This caps the "`$0.50/month` per leaf stack", and isn't worth the extra complexety it'd add. Unless the subscription filter limit gets raised again, this is a hard blocker.
- A minor problem is cross-region variables. I got around it in that PR with a custom parameter-store object. The problem is there's no cross-region equvilent of `self.export_value(some_value)`. If you deploy a leaf stack, then try to update the base-stack alone, the base-stack will try to delete the cross-region variable and fail since something's using it. (The old script [is here](https://github.com/Cameronsplaze/AWS-ContainerManager/pull/102/files#diff-e36e11461b1d85dcce1dd7867c20f480920bfeaf46d61b15a0fff87df22aacb3)).

I had to [undo the pull-request](https://github.com/Cameronsplaze/AWS-ContainerManager/pull/102). I didn't notice the subscription-filter limitation until it was too late, and other work already made it to the repo. I couldn't just revert the first PR. **IF** the subscription-filter on a log group limit ever gets raised, we can re-visit this idea to help limit costs.
