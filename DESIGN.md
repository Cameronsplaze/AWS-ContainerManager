# Design of AWS-ContainerManager

This document describes past and future design choices I've made / will make eventually. If you're looking for the current architecture, README's are sprinkled throughout the project detailing the part that they're in. The farther you get from the root of the project, the more specific they should be for that part.

---

## Past Design Choices

### Public vs Private VPC Subnet

(Went with public subnet)

<details>

<summary>Details</summary>

The idea of this stack was to have ec2 run in a private subnet, and have traffic route through NAT. The problem is you need one NAT per subnet, and they cost ~$32/month EACH. For this project to be usable, it has to cost less than ~$120/year.

Instead of a NAT, you can also have it in the public subnet, take the pubic IP away, and point a Network Load Balancer to it. Problem is they cost ~$194/year.

Instead I'm trying out opening the container to the internet directly, but as minimally I can. Also assume it *will* get hacked, but has such little permissions that it can't do anything

</details>


### EBS vs EFS (Storage)

(Went with EFS)

<details>

<summary>Details</summary>

I went with EFS just because I don't want to manage growing / shrinking partitions, plus it integrates with ECS nicely. By making it only exist in one zone by default, it's about the same cost anyways. It gets expensive if you duplicate storage across AZ's, and we don't need that.

</details>

### ECS: EC2 vs Fargate manager

(Went with EC2. Lambda + Host access makes managing containers cheap and easy.)

<details>

<summary>Details</summary>

- **EC2**:
  - Pros:
    - Networking `Bridge` mode spins up a couple seconds faster than `awsvpc`, due to the ENI card being attached in Fargate.
    - Have access to the instance (container host)

- **Fargate**:
  - Pros:
    - `awsvpc` is considered more secure, since you can use security groups to stop applications from talking. (It says "greater flexibility to control communications between tasks and services at a more granular level". With how this project is organized, each task will have it's own instance anyways. Maybe we can still lock down at the instance level?).
    - `awsvpc` supports both Windows AND Linux containers.

  - Cons:
    - Fargate does not cache images, would have to mirror ANY possible image in ECR. (<https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/pull-behavior.html>).
    - No access to underlying AMI nor the configuration files (`/etc/ecs/ecs.config`)
    - (I don't think?) You can access the instance, which means no SSM to run commands on the host instance. We need this to see if anyone's connected. (The other option is to setup a second container, and monitor the traffic through that, but that eats up task resources for such a simple check. This way it's just a lambda that runs once in a while).

</details>

### StateChange Hook: ECS Task vs ASG Instance

([**ECS Task StateChange Hook**](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs_task_events.html) vs [**ASG Instance StateChange Hook**](https://docs.aws.amazon.com/autoscaling/ec2/userguide/prepare-for-lifecycle-notifications.html). Went with ASG Hook)

<details>

<summary>Details</summary>

- **Pros for ASG**:
  - With ECS Task, there's the possibility of the task failing to start and the hook not running. This means you'll be left with an instance that's up, and no management around it to turn it back down. Starting the management with ASG means this won't happen
  - Will be slightly faster. As the task is trying to get placed, the hook to start up the management is happening in parallel. If you used the task hook, they'd be in series.
- **Cons for ASG**:
  - Part of the management, the lambda cron that checks for connections, will fail if there's no task running. This can happen if it triggers too fast. To get around it, I'll have a Metric + Alarm hooked up to the lambda, and only care about the failure if you get X many in a row. (The management framework being ready TOO fast is a good problem to have anyways).

</details>

### Turn OFF system: Use ASG Hook vs lambda

(Went with ASG Hook)

<details>

<summary>Details</summary>

- **Lambda (lambda-switch-system)**
  - Pros:
    - This is the lambda that turns the system on when route53 sees someone is trying to connect.
    - If you're left in a state where the system is on, but there's no instance, the lambda will trigger every minute all night long. This fixes that by letting the lambda directly turn off the system. (Otherwise if desired_count is already 0, and you SET it to 0, the instance StateChange hook will never trigger).
  - Cons:
    - Because route53 is only in us-east-1, you'd need a lambda in us-east-1 to forward the request to the second lambda. This is a lot of overhead for a simple task. Using the ASG method has other benefits, along with naturally fits into a multi-region architecture.

- **ASG Hook (lambda-instance-StateChange-hook)**:
  - Pros:
    - Originally I went with the other option. It turns out that route53 logs can only live in us-east-1, and with how tightly the "lambda-switch-system" lambda was integrated into the system, that meant that 1) the ENTIRE stack would have to be in us-east-1, or 2) You'd need one lambda to forward the request to the second. Alarms can adjust ASG's directly, so by doing this route, there's no need for a "lambda switch system".
    - This also keeps the system straight forward. (The same part is in charge of both spinning up *and* down the system).
    - Starting or stopping an instance from the console, will naturally trigger the hook, and manage everything around the instance.


</details>

---

## Future Design Choices

### Adding myApplication to the stack

This would let you see the stats for specifically the application you deploy, instead of everything in your account. There's also security hub and a couple extra nice features tied into it.

The problem is I can't get it to deploy. The full writeup is in [this GH discussion](https://github.com/aws/aws-cdk/discussions/30868).

Also myApplication *itself* doesn't cost extra, but idk what to expect from the resources it pulls in itself. If it's too much though, we can always leave it off by default, and make it something you might turn on when deploying a devel stack or something.

<details>

<summary>Code</summary>

```python
# Inside app.py:
from ContainerManager.leaf_stack.my_application_stack import MyApplicationStack
# ...Other stuff here...
    # ...Other stacks here...
    my_application_stack = MyApplicationStack(
        app,
        f"{container_manager_id}-MyApplicationStack",
        description="For setting up myApplication in the AWS Console",
        cross_region_references=True,
        env=main_env,
        application_id=application_id,
        container_name_id=container_name_id,
        # ONLY stacks that use the same env:
        tag_stacks=[manager_stack],
    )
```

```python
# my_application_stack.py, inside ./leaf_stack:

# For setting up myApplication in the AWS Console:
#    - https://aws.amazon.com/blogs/aws/new-myapplications-in-the-aws-management-console-simplifies-managing-your-application-resources/
#    - https://community.aws/content/2Zx50oqaEnUffu7fnD0oXzxNABb/inside-aws-myapplication-s-toolbox-real-world-scenarios-and-solutions

from aws_cdk import (
    Stack,
    Tags,
    aws_servicecatalogappregistry as appregistry,
)
from constructs import Construct


class MyApplicationStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        application_id: str,
        container_name_id: str,
        tag_stacks: list[Stack],
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        ###########################
        ### MyApplication STUFF ###
        ###########################
        ## For cost tracking and other things:
        ## This CAN be used on multiple stacks at once, but all the stacks HAVE to be
        ##     in the same region.
        # https://aws.amazon.com/blogs/aws/new-myapplications-in-the-aws-management-console-simplifies-managing-your-application-resources/
        # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_servicecatalogappregistry.CfnApplication.html
        self.my_application = appregistry.CfnApplication(
            self,
            "CfnApplication",
            name=application_id,
            description=f"Core logic for managing {container_name_id} automatically",
        )

        ## For each stack they pass in, add it to this application
        for stack in tag_stacks:
            # MUST be in the same region as this stack!!
            assert stack.region == self.region, f"Stack '{stack.stack_name}' ({stack.region}) must be in the same region as this stack '{self.stack_name}' ({self.region})"
            ## Adds the 'awsApplication' tag:
            Tags.of(stack).add(self.my_application.attr_application_tag_key, self.my_application.attr_application_tag_value)
            ## TODO: I saw a couple of other tags in the AWS myApplication GUI, add those here too.

            ## Add the Stack to myApplication:
            # https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_servicecatalogappregistry.CfnResourceAssociation.html
            stack_resource_association = appregistry.CfnResourceAssociation(
                self,
                "CfnResourceAssociation",
                application=self.my_application.name,
                # resource=stack.stack_id,
                resource=stack.stack_name,
                resource_type="CFN_STACK",
            )
            # I think this is only required because these are Cfn objects?:
            stack_resource_association.add_dependency(self.my_application)
```

There's also the `AppManagerCFNStackKey` tag key. I think the value is the name of the resources you want to group? Once I redeploy, I'm going to look at adding each ContaienrId as a tag, and group multiple stacks together then.

awsApplication: `arn:aws:resource-groups:<region>:<accountId>:group/<ApplicationName>/<RandomHash>`

</details>

### SSM Session Manager

This would let you SSH into the instance without needing to setup a keypair.

The problem is I can't find the CDK objects for this anywhere, I'm not sure it's something you can automate? Docs say it supports SCP, so it should to SFTP as well. Also since you're no longer using a keypair, it should "just work" after deploying a stack (You don't have to log into aws and grab the keypair). Keeping the SSH port closed is another nice feature.

### Caching ECS Image in AWS

Since caching a image for a task takes place on the instance itself, the "cache" gets wiped every time we spin down. Any caching solution will have to take place in ECR.

One option is the new `Pull through Cache` setting and [cdk construct](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ecr.CfnPullThroughCacheRule.html). If you use Docker or Github though, you're required to setup auth for it. So make this an optional parameter if this path works out. Definitely first **test manually** if you even see a speedup doing this. It might not be worth the extra complexity. ([Blog post here](https://aws.amazon.com/blogs/aws/announcing-pull-through-cache-repositories-for-amazon-elastic-container-registry/))

### Switch Lambdas to use aws-powertools

Look at if [aws powertools](https://docs.powertools.aws.dev/lambda/python/latest/) is worth it, and what features it gives us.

It maybe not installed by default, might have to poke at installing through requirements.txt or lambda layer (not sure which is faster yet).

### Make SSH keys easy to find in the console

No tags, or names get populated to the keys. I have one that's shared between them since idk how you're supposed to tell them apart anyways. Eventually I'd like the option of each container having a unique one, but this blocks that. I've asked about this [here](https://github.com/aws/aws-cdk/discussions/30049) with no luck yet.

I swear I've tried the [params here](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ssm.StringParameter.html#construct-props) too, but it's been a while. Maybe they only take place on creation, not replace? Also there's a key-pair listed in `ec2 key-pair`, but it's actually *stored* in ssm param manager. Maybe those flags only affect one, and I checked the wrong one? It's been a bit, and this isn't MVP, so I'm planning on coming back another time.

### Switch from IPv4 to IPv6

Switch external instance ip from ipv4 to ipv6. Will have to also switch dns record from A to AAAA. May also have security group updates to support ipv6.

Switching because ipv6 is cheep/free, and aws is starting to charge for ipv4. It won't change *much* cost since IPv4 has a free tier we're not breaching yet.

### Only backup select paths in EFS

With Valheim for example, one path contains all the game data you want safe, and the other is the server file that you don't care about. It's only in persistent storage so you don't have to re-download it every launch. Is there a way to only backup the first dir? It might mean that each **path** has to be it's own EFS. If that's the case, we'd also have to update the EC2 instance to mount each one. Is it worth it? I like everything in one EFS since it keeps the console clean. Probably costs less too. You can also see all the paths in one EFS very easily. (Could also just do up to two EFS's maybe. One for backups-enabled and one for not. Although this would mean if someone switched the flag and re-deployed, the new dir would be blank.)

### Rewrite Config Section

Just got something out the door. Now that I know what it should cover, rewrite that area with more linting/casting of objects.

### Shutdown the system when you delete the stack

Right now, if you delete the stack when an instance is up, it'll fail. It fails because the Route53 record is modified, and thus CDK doesn't reconize it's apart of the stack and refuses to delete the "custom resource". There's a couple ways to fix this:

<details>

<summary>Code</summary>

1) Have the makefile spin down the ASG before deleting the stack. It's easiest, but feels hacky.

    - Originally I did this with `aws cli` commands in the makefile like so:

      ```bash
      cdk-destroy-leaf: guard-config-file
      echo "Config File: $(config-file)"
      base_stack_name=`python3 -c "import app; print(app.base_stack_name)"`
      # Get the container ID from the config file:
      container_id=`python3 -c "import app; print(app.get_container_id('$(config-file)'))"`
      # Get the ASG Name from the Container ID:
      asg_name=$$(aws autoscaling describe-auto-scaling-groups \
        --filters "Name=tag:ContainerNameID,Values=Valheim-example" \
        --query 'AutoScalingGroups[0].AutoScalingGroupName' \
        --output text)
      # Set the desired capacity to 0:
      aws autoscaling set-desired-capacity \
        --auto-scaling-group-name $${asg_name} \
        --desired-capacity 0 \
        --honor-cooldown
      ```

      But there's no way to wait for the desired-capacity to finish that I can find. The other option is to move the logic into a python script, and use boto3 calls. This is tempting, but the file would have to live in the root of the project, and the makefile would probably have to use env-vars to pass in the config path to the script. Hence the hackyness of this idea.

2) Use CDK CustomResources to either delete the Route53 record, or spin down the ASG, if a delete is called on the entire stack. (Not sure if spinning down the ASG is possible, but deleting Route53 records definitely is). This does leave yet another lambda in the account per leaf stack, but is a lot more automatic than the other solution.

    - CDK Custom Delete Example [here](https://medium.com/cyberark-engineering/advanced-custom-resources-with-aws-cdk-1e024d4fb2fa)
    - AWS Docs [here](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/template-custom-resources.html) (Not the greatest)

</details>
