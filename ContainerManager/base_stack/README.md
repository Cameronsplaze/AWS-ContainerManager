# Base Stack Summary

This is common architecture between leaf-stacks, combined to reduce costs and complexity.

## Base Stack ([./main.py](./main.py))

Deployed to the same region as you want to run the containers from.

- **VPC**: The overall network for all the containers and EFS. We used a public VPC, because private cost ~$32/month per subnet (because of the NAT). WITH ec2 costs, I want to shoot for less than $100/year with solid usage.
- **SSH Key Pair**: The key pair to SSH into the EC2 instances. Keeping it here lets you get into all the leaf_stacks without having to log into AWS each time you deploy a new leaf. If you destroy and re-build the leaf, this keeps the key consistent too.
- **SNS Notify Logic**: Designed for things admin would care about. This tells you whenever the instance spins up or down, if it runs into errors, etc.
- **Hosted Zone**: *Imports* a hosted zone into this stack. This way you only need one domain, and sub-domains are created off it. Each LeafStackGroup will still need to create their own HostedZone, because otherwise it can only hold a max of two sub-domains. (We use a log-group subscription filter to know when to spin up on a DNS hit, and you can only have two per log group. And you can only have one log group per HostedZone, which also has to exist BEFORE the HostedZone is created...).
