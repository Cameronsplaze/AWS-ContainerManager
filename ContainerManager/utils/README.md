# Utils Functions

## Config Verification and Manipulation

We use the [schema](https://github.com/keleshev/schema) python library to load the config, verify it's structure, and cast objects to what the rest of the code-base expects. This way we can fail fast if (i.e) a cast fails.

- [config_loader.py](./config_loader.py) is for loading/modifying the config for the rest of the code base. It pulls in:
  - [base_config_parser.py](./base_config_parser.py) is for parsing the base config and loading it into a cdk object.
  - [leaf_config_parser.py](./leaf_config_parser.py) is for parsing the leaf config and loading it into a cdk object.
- [check_maturities.py](./check_maturities.py) is for verifying that the maturity strings in the config are valid (case-sensitive). Moved to it's own file to fix [this bug](https://github.com/Cameronsplaze/AWS-ContainerManager/pull/180)
- [sns_subscriptions.py](./sns_subscriptions.py) is for sns logic that is used in both the base and leaf stacks. It parses a config and loads it as cdk objects.
