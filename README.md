# GameManagement

## Quick Start

An AWS manager to run games in the CLOUD!!!

To create your own stack:

1) Setup access keys. You can figure it out.

2) Run something like:

```bash
aws --region us-west-2 cloudformation deploy --template-file stack.yml --stack-name STACK_NAME_HERE
```

There's params inside `stack.yml` that you can override, but defaults to minecraft for now.

## Devel Stuff

Setup a basic virtual environment, with the different packages:

```bash
sudo apt install python3-pip python3-virtualenv # I think? It's been a bit since I installed this. Don't use the (pip install virtualenv) version though
virtualenv --python=python3 ~/GameManager-env
source ~/GameManager-env/bin/activate
python3 -m pip install boto3
```