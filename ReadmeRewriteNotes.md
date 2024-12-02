



`Examples/README.md`

- Make sure to link to utils/config-parser.py somewhere
- Move Github workflows shoutout out of this file
- Rewrite as mentioned in GH issues, lets you link to each key
- Link `Issues or Discussions` in #1 at the bottom to the GH links

Move over from main README.md:

```

### What to do if my container stays on too long or randomly spins down?

This likely means the `Threshold` for watching container traffic is too far off. Go into the `ContainerManager-<container-id>-Dashboard` and check the `Alarm: Container Activity` Graph. It'll tell you how much traffic is going into the container in Bytes/Second.

- **If it's staying on too long after people disconnect**, you'll have to raise the threshold. Make sure everyone is disconnected, and wait ~10 minutes. Look at the highest point it reaches in that time, and set the `Threshold` just above that. (If someone *just* disconnected, give the container a bit to become "stable" before starting the 10min count).
- **If it's spinning down too quickly**, you'll have to lower the threshold. Do the same as above to figure out *where* to set it.
```


---
`ContainerManager/README.md`

TODO: Change the `Base Stack Config Options` format to match the new "allow command linking" style. The same as the Examples/README.md is going to use.

---
`ContainerManager/leaf_stack/README.md`

## Mermaid Event Graph (Not Dependency Graph. Map the ideal "If A then B...")

## Components

    ### - Each file has one...


