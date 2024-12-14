# Utils Functions

TODO: All this. I want to re-work this area of the code base once mvp is solid.

Tldr:

- [config_loader.py](./config_loader.py) is for loading/modifying the config for the rest of the code base.
- [get_param.py](./get_param.py) is for loading parameters in CDK, but still being able to access the value you pass in.
- [sns_subscriptions.py](./sns_subscriptions.py) is for sns logic that is used in both the base and leaf stacks. It parses a config and loads it as cdk objects.

## Moving Variables between the Stacks

This area became very complicated very fast. The main issue is I **can't** use `cross_region_references` on stack creation to simplify everything. If I did, and you `deploy base => deploy leaf => deploy base`, that final "deploy base" would try to delete the automatic exports created by "deploy leaf". There's no equivalent `export_value` that same-region exports have.

Technically there is one spot I can use `cross_region_references` in this project, from the "main manager" stack to the "start system" stack. The problem is if I enable it, there's no way to say "but block cross-region references from the base stack". It'll be too easy to release a change that includes the automatic exports from the base stack, and block people from re-deploying it.

### Cross-Region: Moving Values between the Base and Leaf Stacks

On the **base_stack** side: use [export_cross_zone_var.py](./export_cross_zone_var.py) to create the export (ssm parameter) in the region you want to use it. (Originally I did the other method, of *importing* it from other regions. The problem is the stack consuming it can't see when it's updated. So to get around it, it has to have a part with datetime.now(), and change *every single update*. [More details here](https://github.com/aws/aws-cdk/blob/main/packages/aws-cdk-lib/core/adr/cross-region-stack-references.md#alternatives)).

On the **leaf_stack** side: Use [ssm.StringParameter.value_from_lookup](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ssm.StringParameter.html#static-valuewbrfromwbrlookupscope-parametername-defaultvalue). This is the best one because it'll re-fetch the value every synth. Because you're going between the base and leaf stacks, the base stack exists and this succeeds. (It'll just hang if the stack doesn't exists on synth. Doesn't matter if it's "about" to be deployed.)

### Cross-Region: Moving Values between the Inner-Leaf Stacks

This is if you're trying to get a variable from the "main leaf stack" in a region of your choice, to the "start system" stack in us-east-1. Both stacks are apart of the same app.

Exporting is the same as the [base_stack above](#cross-region-moving-values-between-the-base-and-leaf-stacks).

To import, you need to use [ssm.StringParameter.from_string_parameter_attributes](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ssm.StringParameter.html#static-fromwbrstringwbrparameterwbrattributesscope-id-attrs) **instead** of [ssm.StringParameter.value_from_lookup](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_ssm.StringParameter.html#static-valuewbrfromwbrlookupscope-parametername-defaultvalue). The "main" leaf stack doesn't exist during deploy, so the "value_from_lookup" will hang. I'm worried this means if the exported value is ever replaced, the "start system" stack will assume it's not changed and use the old value. I just don't know any way around this without hitting the other problems mentioned in this section.
