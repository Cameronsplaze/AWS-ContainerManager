# GameManagement

An AWS manager to run games in the CLOUD!!!

To create your own stack:

1) Setup access keys. You can figure it out.

2) Run something like:

```bash
aws --region us-west-2 cloudformation deploy --template-file stack.yml --stack-name STACK_NAME_HERE
```

There's params inside `stack.yml` that you can override, but defaults to minecraft for now.
