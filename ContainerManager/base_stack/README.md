# Base Stack Summary

This is common architecture between leaf-stacks, combined to reduce costs and complexity.

## Base Stack Main ([main.py](./main.py))

Deployed to the same region as you want to run the containers from.

- **VPC**: The overall network for all the containers and EFS. We used a public VPC, because private cost ~$32/month per subnet (because of the NAT). WITH ec2 costs, I want to shoot for less than $100/year with solid usage.
- **SSH Key Pair**: The key pair to SSH into the EC2 instances. Keeping it here lets you get into all the leaf_stacks without having to log into AWS each time you deploy a new leaf. If you destroy and re-build the leaf, this keeps the key consistent too.
- **SNS Notify Logic**: Designed for things admin would care about. This tells you whenever the instance spins up or down, if it runs into errors, etc.

## Base Stack Domain ([domain.py](./domain.py))

Deployed to `us-east-1`, since Route53 logs can only go there.

- **Route53 HostedZone**: The base domain for all the leaf stacks. This is where the DNS records will be created for each leaf stack. The leaf stacks add their DNS record to this, and watch this log group for when their specific DNS record gets a query.
