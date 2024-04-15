

## Using this config for management, so you can have BOTH yaml and Env Vars:
# https://github.com/mkaranasou/pyaml_env
from pyaml_env import parse_config

# The method is incase there's any special logic I end up needing
# to add. For now it's just a place holder I guess
def load_config(path: str) -> dict:
    return parse_config(path)

# There's also an argument for moving `sns_subscriptions` to this file, and anything else
# that both config types share in common (base and leaf configs). Then add:
#      `subscriptions = config.get("Alert Subscription", [])`
# to the sns_subscriptions.add_sns_subscriptions() method too, it'll be clear it takes a config.
