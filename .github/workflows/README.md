# GitHub Actions

## Dependabot auto updates

There's a lot of tweaks I had to do to get this working. Will come back to at some point and re-write this readme. To include:

- Disabled PR code having to be up to date with base. If two dependabot PRs are open at the same time, the second one will fail to merge.
  - We can technically get around this by setting the max-pr to 1 in each config block, then having each block run a different day of the week. This feels really hacky though...
- Added CODEOWNERS file, but had to disable on the files dependabot touches. There's no way to add apps to CODEOWNERS. (More details in the CODEOWNERS file itself.).
- Added a list of required actions to main. At first didn't want to maintain the list, but you get a nice clear label on all the actions, so you can easily see if you add an action later and forget to add it to the list. (I tried having the action run a `gh pr` command to wait, but it ended up waiting on itself...).
- In [dependabot.yml](../dependabot.yml), added a `groups` section. This makes all updates happen under a single PR. That way if 3 updates get created, you don't merge all 3 at the same time and try to do 3 deployment updates at once.
- Any actions you want to block dependabot updates from merging, MUST be **required workflows** in the repo settings. They also can't contain the `on.<trigger>.paths` key. If they do, and the paths isn't in the PR, you won't be able to merge it. (It just freezes saying "Expected — Waiting for status to be reported")

## main-pipeline-cdk.yml

On PR's, it synths all the cdk stacks, and when merged, will deploy them to main.

- It's specifically designed to synth on PR's, and deploy on push's, but not vise-versa. This way when it merges to main, you're not trying to synth and deploying at the same time. (synth-ing THEN deploying is pointless, since it had to successfully synth to be merged...).
- These run on PR's even though they only have a `push` trigger, because of how GH does commits behind the scenes. I have these all listed as `required` in the branch protection rules, so GH will still wait for them to finish before letting you merge the branch.

## Add another Container to cdk-deploy in main-pipeline-cdk.yml

I made this different than `cdk-synth`. For synth, it should run on EVERY config to make sure they always work. For deploy, it'll change randomly depending on what games you find fun at the time.

1) Add the container path as a Github Variable `DEPLOY_EXAMPLES`. Each is a path, starting after `./Examples/` in this repo. For example:

    ```txt
    ./Minecraft-example.yaml
    ./Valheim-example.yaml
    ```

2) Create a new Github Environment, with the same name. For example, `./Minecraft-example.yaml`.

3) If there's secrets/variables you want passed to the container config, add a variable to the environment called `CONTAINER_VARS`. This should be a list of key-value pairs, each on a new-line. For example:

    ```txt
    # NO SPACES! They won't parse correctly.
    SERVER_NAME=My-Minecraft-Server
    SERVER_PASSWORD=super_secure_pass
    ```

## Forking this Repo

- TODO: Finish this section. Make sure to include:
  - Which secrets/vars you need to set in GH. (Including the list of examples to deploy)
