# REA native-analysis runbook for SC4

This runbook connects [REA](https://rea.tools/) to the SC4 behavioral
distillation lab. REA is an analysis assistant, not a source of SC4 code or
assets. Use only a legitimately acquired local executable and keep analysis
outputs private unless they are independently written observations.

## Current state

- Project-side target manifest tool: `tools/rea_target_manifest.py`.
- Current machine: Wine, `winedbg`, and GDB are present.
- REA 6.5.0 is connected to Codex and skill version 42 is installed/aligned.
  Restart Codex before expecting the MCP tools in this already-running session.
- Native provider: Ghidra 12.1.4 + Temurin JDK 21.0.12 are configured in the
  user-local REA environment. Hopper was deliberately skipped because its
  setup is a system package installation.
- System Node remains `18.19.1`; user-local fnm provides Node `24.22.0` for
  REA. Current REA setup requires Node 22.19+, 24.11+, or 26+.
- No live SC4 process or `.sc4` save is present in the workspace, so runtime
  validation waits for the user's installed game and a controlled city.

## Safety and data boundary

Do not commit the executable, extracted strings, disassembly databases, raw
memory, save files, or proprietary assets. Commit only independently authored
documentation, schemas, scripts, and summarized observations. The manifest
records a path, size, timestamp, SHA-256, and PE header metadata; it does not
copy the target or extract code.

## One-time host setup

1. Install or select a supported Node version in the user account. Do not
   replace the system Node package just for this lab.
2. Run REA setup for Codex and review its proposed configuration changes:

   ```text
   npx rea-agents@latest setup --client codex
   ```

   REA keeps a configuration backup and asks before applying the connection.
   Restart Codex after approval.
3. Install/configure one native provider. The preferred free path is Ghidra
   with a 64-bit JDK 21+; record `GHIDRA_INSTALL_DIR` and `JAVA_HOME` in the
   shell used for setup. Hopper is an alternative where licensed/available.
4. Verify both connection and provider before opening SC4:

   ```text
   npx -y rea-agents@latest doctor --client codex --json
   npx -y rea-agents@latest doctor --provider ghidra --json
   ```

   Treat `healthy: true` as setup success. A missing provider is a setup
   blocker, not evidence about SC4.

## First SC4 investigation

Use the exact executable that will be run under Wine. Generate a private
manifest outside the repository:

```bash
python3 tools/rea_target_manifest.py \
  "/absolute/path/to/SimCity 4.exe" \
  --provider ghidra \
  --out /tmp/opensc4-rea-sc4-target.json
```

Then ask REA one narrow question at a time, starting with static structure:

```text
Use REA with Ghidra to inspect /absolute/path/to/SimCity 4.exe.
List functions and strings related to save/load and city simulation updates.
For each candidate, give the address, callers, constants, and confidence.
Do not patch, inject into, or modify the executable.
```

The first useful artifact is a candidate table, not a guessed memory map:

| Candidate | Evidence | Next check | Status |
| --- | --- | --- | --- |
| save/load path | strings + callers | controlled save before/after | unverified |
| simulation tick | callers + timing | pause/run observation | unverified |
| treasury/statistic path | constants + writes | runtime value change | unverified |

### Completed static preflight

REA's provider-free PE resource parser completed against both local backup
executables. Each was identified as a complete PE32/x86 image with 23 resource
records. They have different SHA-256 identities, so do not mix analysis notes
between them. Resource inventory is provenance only: it does not identify
simulation functions, and the parser does not decode opaque payloads or observe
runtime loading.

## Runtime correlation loop

1. Start SC4 with the user's normal mod configuration and record the executable
   hash from the manifest.
2. Create a tiny synthetic city and record its visible date/treasury.
3. Use `tools/memory_observatory.py` only for read-only candidate scanning and
   sampling. Start with values that are already visible in the UI.
4. Save before and after exactly one controlled action. Use
   `tools/reference_capture.py` to record metadata and changed save chunks; it
   intentionally does not dump save bytes.
5. Require the same candidate to survive a second run, a reload, and a changed
   input before calling it verified.
6. Write the result as a behavioral observation in the lab schema. Never put
   an absolute pointer or raw proprietary bytes into a committed fixture.

## Controlled tax-path investigation

For the exact executable hash recorded in the tax-path milestone, the budget
object's live vtable resolved a tax getter at `+0x90` and setter at `+0x94`.
The getter indexes twelve floats at `this+0x70+index*0x80`; the setter checks
only the upper bound (`index < 12`). This was established from native
instructions and then verified against a live process. It is not a portable
address map.

If a user explicitly requests a temporary in-process tax experiment, rediscover
the object pointer from the current process global, verify the executable hash,
call only the proven setter with indices `0..11`, and read the fields back.
Never add a generic arbitrary-memory writer to the observatory, never use a
negative index, and never treat a changed UI cache as proof that tax income was
recalculated. Record the experiment as runtime metadata outside Git. The full
result and formula boundary are in
`docs/milestones/sc4-tax-distillation-v0.1.md`.

## First milestones

1. **REA connected**: both doctors healthy and Codex sees the REA tools.
2. **Target identified**: private manifest records the exact executable hash,
   architecture, and provider.
3. **Static candidate**: one save/load or simulation-tick candidate has caller
   and constant evidence.
4. **Runtime candidate**: one visible value is correlated across two sessions
   without hardcoding an absolute address.
5. **Behavioral rule**: one narrow rule is independently written and compared
   against held-out SC4 observations.

Do not jump from static disassembly directly to an OpenGlassBox implementation.
The distillation protocol in `docs/distillation.md` still governs hypotheses,
provenance, confidence, and held-out observations.

## Useful CLI fallback

Once the provider is configured, REA's native CLI can query a known function or
address without changing the executable:

```bash
npx -y rea-agents@latest function \
  "/absolute/path/to/SimCity 4.exe" \
  0x00400000 --provider ghidra --json
```

Replace the address with a candidate returned by the analysis. Keep the JSON
result local; commit only a concise, independently authored interpretation.

## REA/Ghidra timeout fallback

The current LAA backup is a legacy PE32 image with stripped symbols, no local
PDB, and missing Windows import libraries. REA's Ghidra provider was healthy,
but its `analyze`, `search`, and focused `function` operations each reached the
330-second bridge timeout while this target was being enumerated. Preserve that
failure as a provider limitation; do not call it evidence that the target has
no functions.

For a bounded interim ledger, run the repository fallback locally:

```bash
python3 tools/sc4_static_candidates.py \
  "/absolute/path/to/SimCity 4.exe" \
  --out /tmp/opensc4-sc4-static-candidates.json
```

It records selected named strings, PE virtual addresses, and static `objdump`
instruction references only. It does not establish function boundaries,
calling conventions, authoritative state, or runtime writes. Use it to choose
the next REA/Ghidra address, not as a substitute for REA evidence.

## Private evidence-pack export

The bounded ledger can now be packaged with target provenance, categorized
hypotheses, REA evidence IDs, runtime requirements, and the data boundary:

```bash
python3 tools/sc4_evidence_pack.py \
  "/absolute/path/to/SimCity 4.exe" \
  --provider ghidra \
  --rea-evidence-id "<REA evidence id>" \
  --runtime-snapshot /tmp/opensc4-sc4-live-snapshot-01.json \
  --out /tmp/opensc4-sc4-evidence-pack.json \
  --markdown-out /tmp/opensc4-sc4-evidence-pack.md
```

This is the project's local equivalent of an export: it extracts structured
metadata and candidate leads, not executable bytes or proprietary data. The
tool refuses output paths inside the Git repository. The current LAA backup
produced 185 named candidates and 57 retained leads, including `g_funds`,
`g_population`, `g_date`, `g_power_consumed`, `SimulationClock`, and
`LoadCity`. Every lead remains `candidate_unverified` until it survives a
controlled runtime scan, save/reload, and second-session check.

When `--runtime-snapshot` is supplied, the pack records only the snapshot
schema, PID, process name, timestamp, region count, and the explicit
`raw_bytes_recorded=false` boundary. It does not embed the snapshot or any
memory contents.
