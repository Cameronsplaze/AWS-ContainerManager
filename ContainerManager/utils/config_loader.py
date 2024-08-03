

## Using this config for management, so you can have BOTH yaml and Env Vars:
# https://github.com/mkaranasou/pyaml_env
from pyaml_env import parse_config




#######################
## LEAF CONFIG LOGIC ##
#######################

# TODO: Re-write all of this, maybe create ec2.port objects instead of passing the dicts around all over the place.
#         (And maybe do with other dicts here too)



def load_leaf_config(path: str) -> dict:
    config = parse_config(path)


    #######################
    ### WATCHDOG CONFIG ###
    #######################
    watchdog = config.get("Watchdog", {})


    # Default changes depending on protocol used:
    if "Threshold" not in watchdog:
        if watchdog["Type"] == "TCP":
            watchdog["Threshold"] = 0
        elif watchdog["Type"] == "UDP":
            # TODO: Keep an eye on this and adjust as we get info from each game.
            #           - Valheim: No players ~0-15 packets. W/ 1 player ~5k packets
            watchdog["Threshold"] = 32

    config["Watchdog"] = watchdog

    return config

# There's also an argument for moving `sns_subscriptions` to this file, and anything else
# that both config types share in common (base and leaf configs). Then add:
#      `subscriptions = config.get("Alert Subscription", [])`
# to the sns_subscriptions.add_sns_subscriptions() method too, it'll be clear it takes a config.
