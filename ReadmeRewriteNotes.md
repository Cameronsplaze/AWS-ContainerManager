# Base Readme

This should be the minimal to use/start with the project. Don't go into architecture here.

## Quick Start

### Setting up AWS (First Time)

### Deploying the Stacks
See `Advanced Deployments` for more specific info.
#### Base Stack
#### Leaf Stack

### Connecting to the Container

### Cleaning up after



## Running Commands on the Host / Accessing Files

### SSM Session Manager
### SSH into the Host
### Moving files from Old EFS to New


## Writing your own Config

See "here" for info on writting config files

### Configurable Alarms in the Stack

Link to the Threshold in Examples/README.md, for how to find/set *that* value. (In that area, explain where to see the alarm going off. Both in the dashboard, and in metrics if dashboard is disbaled.)

And talk about the other two quickly here too. Link to `leaf_stack/README.md#watchdog`'s section once it exists.

## Cost of Everything

## Advanced Deployments

### Deploy / Destroy

Examples with container-id, maturity, and container-id

### Synth

Just link to developing section for this, that's where you'd need it.

### Automating Deployments (See GH/Workflows readme.md)

## Learning / Developing on the Architecture

Link directly to basic architecture diagram.

Go over how docs are structured, with each directory getting a more-specific readme


---
`Examples/README.md`

- Make sure to link to utils/config-parser.py somewhere
- Move Github workflows shoutout out of this file
- Rewrite as mentioned in GH issues, lets you link to each key
- Link `Issues or Discussions` in #1 at the bottom to the GH links

---
`ContainerManager/README.md`

## Go Over Basic Architecture Design (plus leaf_stack picture)

Make sure you're clear leaf_stack's picture is just *it*'s logic.

## Design of Base Stack + Leaf Stack

### Quick overview of files in this direct folder

## Base stack config options

---
`ContainerManager/leaf_stack/README.md`

## Mermaid Event Graph (Not Dependency Graph. Map the ideal "If A then B...")

## Components

### - Each file has one...


