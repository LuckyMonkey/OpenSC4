# Runbook: development iteration and Git sync

Use this loop for every focused milestone. It is designed to preserve local
game data, keep the branch reviewable, and leave evidence for the next session.

## 1. Preflight

```sh
git status --short
git fetch origin
git log --oneline --decorate -5
bash tools/check_data_boundary.sh
```

Do not reset or discard existing user changes. If the worktree is dirty, keep
unrelated changes separate and inspect overlapping files before editing.

## 2. Choose one evidence-producing slice

Prefer one of these shapes:

- a deterministic regression fixture;
- a before/after benchmark;
- a documented edge-case fallback;
- a plain-data backend/interface seam;
- an independently written behavioral specification.

Do not combine a rendering optimization, simulation rule, and save migration in
one untestable change.

## 3. Verify locally

Fast checks for parser/backend/docs-only work:

```sh
git diff --check
godot --headless --path . --import
godot --headless --path . res://tools/SyntheticBackendSmoke.tscn
godot --headless --path . res://tools/ParserFixtureSmoke.tscn
bash tools/check_data_boundary.sh
```

For city or renderer work, also run:

```sh
bash tools/run_baseline.sh /tmp/opensc4-iteration Timbuktu "Big City Tutorial"
```

For a data-only or headless check, explicitly skip screenshots:

```sh
SC4_SKIP_SCREENSHOT=1 bash tools/run_baseline.sh \
    /tmp/opensc4-iteration-headless Timbuktu "Big City Tutorial"
```

The baseline manifest records commit, dirty-file count, Godot version,
resolution, and opt-in performance profiles. Screenshot capture is valid when
the log contains `SCREENSHOTS DONE`; the known renderer shutdown 134 is tracked
separately from capture completion.

## 4. Document before committing

Update the smallest relevant document:

- `docs/project-status.md` for verified state;
- `docs/roadmap.md` for milestone status;
- `docs/future-work.md` for unresolved work;
- a runbook for repeatable commands;
- `docs/milestones/` for a completed evidence package.

State what was not tested. Never add reference values that were not observed.

## 5. Commit and synchronize

```sh
git diff --check
git status --short
git add <explicit-files>
git commit -m "Describe the evidence-producing milestone"
git push origin improve-ultrawide-and-city-bootstrap
git status --short
git log -1 --oneline --decorate
```

Use explicit paths when staging. A successful sync ends with a clean worktree
and local `HEAD` matching `origin/improve-ultrawide-and-city-bootstrap`.

## Triage

| Symptom | First check | Interpretation |
| --- | --- | --- |
| import failure | `import.log` | script/class/resource regression |
| parser fixture failure | `parser.log` | malformed input handling changed |
| no `SWEEP COMPLETE` | `city.log` | load, timeout, or shutdown before sweep |
| screenshot lacks marker | `screenshot.log` | display startup or scene failure |
| marker plus status 134 | screenshot tail | capture completed; investigate cleanup separately |
| performance changed | manifest plus probe output | compare same renderer, city, pose, and profile |

Keep generated logs and screenshots in `/tmp` or another local output folder;
do not commit them unless they contain no protected game content.
