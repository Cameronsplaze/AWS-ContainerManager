# Utils Functions

TODO: All this. I want to re-work this area of the code base once mvp is solid.

Tldr:

- [config_loader.py](./config_loader.py) is for loading/modifying the config for the rest of the code base.
- [outputs.py](./outputs.py) is for loading outputs from the CDK stack. (Things you want to save in the console, but DON'T want to constantly modify from parameters).
- [parameters.py](./parameters.py) is for loading parameters in CDK, but still being able to access the value you pass in.
- [sns_subscriptions.py](./sns_subscriptions.py) is for sns logic that is used in both the base and leaf stacks. It parses a config and loads it as cdk objects.
