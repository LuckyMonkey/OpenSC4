# Runbook: release and contribution hygiene

Before pushing a change:

```sh
git diff --check
godot --headless --path . --import
bash tools/run_baseline.sh /tmp/opensc4-release-check
```

Confirm that:

- no `.dat`, `.sc4`, executable, DLL, plugin, or extracted asset is tracked;
- reference observations do not contain original game data;
- new tolerances are reviewed independently of candidate code;
- OpenGlassBox remains an external pinned dependency unless licensing and build
  ownership are documented;
- screenshots and logs containing game content remain outside Git;
- the commit describes what was verified and what remains untested.

If a test needs the user's installation, document the exact local command and
expected result instead of adding the installation to CI.
