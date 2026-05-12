# plugins/

OpenClaw plugin manifest cache. The real `installs.json` is
auto-generated from the bundled plugins shipped with the upstream
`openclaw` npm package and contains the absolute path of every plugin's
`openclaw.plugin.json` on the local machine — therefore gitignored.

## How to populate

```bash
openclaw plugins registry --refresh
```

Then enable / disable individual plugins:

```bash
openclaw plugins enable nvidia
openclaw plugins disable telegram
```
