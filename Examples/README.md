# Writing your own Config Files

## TODO

## Gotchas

- **For backups**: We use EFS behind the scenes. Use the `Volume.EnableBackups` if you want backups. **IF you do it inside the container**, you'll be doing backups of backups, and pay a lot more for storage. Plus if your container gets hacked, they'll have access to the backups too.
- **For updating the server**: Since the container is only up when someone is connected, any "idle update" strategy won't work. The container has to check for updates when it first spins up. Then what to do depends on the game.
  - For minecraft, it won't let anyone connect until after it finishes. It handles everything for you.
  - For Valheim, it'll let you connect, then everyone will get kicked when it finishes so it can restart (3-4min into playing). OR you can have it *not* restart, and you'll get the update after everyone disconnects for the night.
- **Whitelist inside of the Configs**: All the containers I've tested so far provide some form of this. You can use it, but it means you have to re-deploy this project every time you make a change. It takes forever, and (might?) kick everyone for a bit. If you can, use the game's built-in whitelist feature instead. (Unless maybe you don't expect it changing often, like with an admin list.)
