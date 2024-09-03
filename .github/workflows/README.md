# GitHub Actions

## Dependabot auto updates

There's a lot of tweaks I had to do to get this working. Will come back to at some point and re-write this readme. To include:

- Disabled PR code having to be up to date with base. If two dependabot PRs are open at the same time, the second one will fail to merge.
  - We can technically get around this by setting the max-pr to 1 in each config block, then having each block run a different day of the week. This feels really hacky though...
- Added CODEOWNERS file, but had to disable on the files dependabot touches. There's no way to add apps to CODEOWNERS. (More details in the CODEOWNERS file itself.).
- Added a list of required actions to main. At first didn't want to maintain the list, but you get a nice clear label on all the actions, so you can easily see if you add an action later and forget to add it to the list. (I tried having the action run a `gh pr` command to wait, but it ended up waiting on itself...).
- Removed the `pull_request` trigger from main actions. I might have to revisit this. When it was both `pull_request` AND `push`, the actions would run twice. Since they're required, even if they're `push`, the action will wait on them. Since the dependabot PR's JUST got created when opened, the action will run on those too. Plus you still get normal checks on all the pushes you do anyways. So maybe it's fine to just have them run on `push` and "not" `pull_request`?

## cdk-synth-examples.yml

Going to rename soon, but it's basically the main pipeline. On PR's, it synths all the cdk stacks, and then (WIP) will hopefully deploy them when merged to main. I still need to think of a good way to exclude some of the stacks that I'll want to synth, but NOT deploy.

- It's specifically designed to synth on PR's, and deploy on push's, but not vise-versa. This way when it merges to main, you're not trying to synth and deploying at the same time. (synthing THEN deploying is pointless, since it had to successfully synth to be merged...).
- These run on PR's even though they only have a `push` trigger, because of how GH does commits behind the scenes. I have these all listed as `required` in the branch protection rules, so GH will still wait for them to finish before letting you merge the branch.
