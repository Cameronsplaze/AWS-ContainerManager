# GitHub Actions

## Dependabot auto updates

There's a lot of tweaks I had to do to get this working. Will come back to at some point and re-write this readme. To include:

- Disabled PR code having to be up to date with base. If two dependabot PRs are open at the same time, the second one will fail to merge.
  - We can technically get around this by setting the max-pr to 1 in each config block, then having each block run a different day of the week. This feels really hacky though...
- Added [CODEOWNERS](../CODEOWNERS) file, but had to disable on the files dependabot touches. There's no way to add apps to CODEOWNERS. (More details in the CODEOWNERS file itself.).
- Added a list of required actions to main. At first didn't want to maintain the list, but you get a nice clear label on all the actions, so you can easily see if you add an action later and forget to add it to the list. (I tried having the action run a `gh pr` command to wait, but it ended up waiting on itself...).
- In [dependabot.yml](../dependabot.yml), added a `groups` section. This makes all updates happen under a single PR. That way if 3 updates get created, you don't merge all 3 at the same time and try to do 3 deployment updates at once.
- Any actions you want to block dependabot updates from merging, MUST be **required workflows** in the repo settings. They also can't contain the `on.<trigger>.paths` key. If they do, and the paths isn't in the PR, you won't be able to merge it. (It just freezes saying "Expected — Waiting for status to be reported")

## main-pipeline-cdk.yml

On PR's, it synths all the cdk stacks, and when merged, will deploy them to main.

- It's specifically designed to synth on PR's, and deploy on push's, but not vise-versa. This way when it merges to main, you're not trying to synth and deploying at the same time. (synth-ing THEN deploying is pointless, since it had to successfully synth to be merged in the first place...).
- These run on PR's even though they only have a `push` trigger, because of how GH does commits behind the scenes. I have these all listed as `required` in the branch protection rules, so GH will still wait for them to finish before letting you merge the branch.

## Automatic Deployments: Whitelisting/Adding a Container

I made this different than `cdk-synth`. For synth, it should run on EVERY config to make sure they always work. For deploy, it'll change randomly depending on what games you find fun at the time.

1) Add a new line to the **Github Variable** `DEPLOY_EXAMPLES`. Each line is a path, starting **after** `./Examples/` in this repo. For example, it might contain:

    ```txt
    ./Minecraft-example.yaml
    ./Valheim-example.yaml
    ```

2) Create a new Github Environment, with the same name as the line you added. For example, `./Minecraft-example.yaml`.

3) Inside that environment, you can create any number of variables / secrets specific to that deployment. Since they're apart of the environment, they won't be exposed to the other containers either. They'll be environment variables when the action deploys, so reference them directly in the `./Examples/<container>` yaml file. I.e:

    ```txt
    Github Secret: ${{ secrets.SERVER_PASS }}
    Or Variable: ${{ vars.SERVER_NAME }}
    ```

    Can be referenced in the yaml file as:

    ```yaml
    !ENV ${SERVER_PASS}
    !ENV ${SERVER_NAME}
    ```

    Technically to do this, all secrets/variables are turned into environment variables in the action. However, even if the container is untrusted, if you don't pass the env-vars to the container in the `./Examples/<container>` yaml file, it won't be able to see them.

**Finally**: If you decide to remove it to save money, you can just remove the one line from `DEPLOY_EXAMPLES`, then delete the stack. This lets you keep the environment around with all the variables, in case you want to re-deploy it later.

## Forking this Repo

I specifically designed all the automation, so that if it's forked, you can re-use it and customize it to your own needs without conflicting with the base. The way of doing this was relying on GitHub's secrets/variables when deploying.

1) Setup [AWS OIDC](https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services). How I do it personally is at [Cameronsplaze/AWS-OIDC](https://github.com/Cameronsplaze/AWS-OIDC). It's only one-per-account, so it can't be in this repo.
2) Repository **Secrets** you'll want declared (in the 'core', NOT in any environment):

    - **AWS_ACCOUNT_ID**: Your AWS Account ID.
    - **DOMAIN_NAME**: The domain name of your Route53 Hosted Zone.
    - **HOSTED_ZONE_ID**: The ID of your Route53 Hosted Zone.
    - **EMAIL**: The email for receiving alerts for everything. (Might turn this into a list at some point, the yaml config supports that already anyways...)

3) Repository **Variables** you'll want declared (in the 'core', NOT in any environment):

    - **AWS_DEPLOY_ROLE**: The role to use with OIDC. (If you're using my repo, it's `github_actions_role`).
    - **AWS_REGION**: The region to deploy to. (Some HAS to be deployed to `us-east-1`, this is everything else that's not restricted).
    - **DEPLOY_EXAMPLES**: The list of container config paths to deploy, each on their own line. (See '[Automatic Deployments](#automatic-deployments-whitelistingadding-a-container)' for details).

4) Follow '[Automatic Deployments](#automatic-deployments-whitelistingadding-a-container)' for adding a new container to deploy. Can go through any number of times.
