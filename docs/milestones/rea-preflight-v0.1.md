# REA preflight milestone v0.1

Status: complete for provider-free artifact inspection; native analysis pending.

## Achieved

- Added `tools/rea_target_manifest.py`, a metadata-only PE manifest generator.
- Added `docs/runbooks/rea-sc4.md` with setup, target identity, evidence, and
  runtime-correlation procedures.
- Installed REA 6.5.0's user-owned Codex MCP registration and reverse-engineer
  skill version 42 using user-local Node 24.22.0.
- Verified the Codex registration and skill with REA doctor:
  - Node: healthy.
  - Codex registration: aligned.
  - Skill: installed and aligned.
- Ran REA's read-only PE resource inspection on both available SC4 backup
  executables. Both were complete PE32/x86 images with 23 resource records.

## Explicit limits

- The current Codex process must be restarted before newly registered REA MCP
  tools can appear in-session.
- No Ghidra, Hopper, or IDA provider is configured. Therefore no function list,
  decompilation, call graph, or simulation-rule claim is established yet.
- No live SC4 process or city save is available in the workspace, so runtime
  correlation remains pending.
- No executable, save, raw memory, extracted strings, or disassembly database
  was added to the repository.

## Next milestone: native candidate ledger

1. Restart Codex and confirm REA tools are visible.
2. Install/configure Ghidra plus JDK 21+ separately, or explicitly approve a
   different native provider.
3. Open the exact executable selected by the target manifest.
4. Produce a small static candidate ledger for save/load, simulation tick, and
   one visible city statistic.
5. Correlate one candidate with two controlled SC4 runs using the existing
   memory observatory and save metadata capture tools.

The acceptance criterion is a cited, reproducible candidate with explicit
unknowns—not a guessed SC4 object model.
