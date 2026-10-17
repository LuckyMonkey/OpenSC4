# SC4 behavioral distillation — handoff, runbook, roadmap

Snapshot 2026-10-17. Branch `improve-ultrawide-and-city-bootstrap` of
[LuckyMonkey/OpenSC4](https://github.com/LuckyMonkey/OpenSC4).

## 1. What this is

OpenSC4 is a Godot reimplementation of SimCity 4 that loads the original
game's data files. Rendering is well along; **simulation is the hard part**:
SC4's rules (taxes, demand, growth, power, traffic, …) were never published.

"Distillation" here means recovering those rules from the **running retail
game** and writing them down as independently authored equations with
evidence, so they can be reimplemented. We do not copy code or ship game
data. Every claim must be backed by observation, and promoted only after it
predicts something it was not fitted to.

The method that works best so far is **dynamic**: read and write the live
game's memory, watch what changes at month boundaries, perturb one input,
check the prediction, then confirm the function in the disassembly.

## 2. Environment

| Item | Value |
| --- | --- |
| Game | Steam SimCity 4 Deluxe (AppID 24780), Proton Experimental, Linux |
| Executable | `Apps/SimCity 4.exe`, PE32 x86, 7,876,608 bytes |
| SHA-256 | `f512a405c1e3f0dc82b784d5d9619f4751f03d0905d9d6b94cd528f1d4be1153` |
| Image base | `0x00400000` (no ASLR in practice) |
| Process | `pgrep -f 'S:\\steamapps\\common\\SimCity 4 Deluxe\\Apps\\SimCity 4.exe'` |
| Tools | Python 3 + numpy, gdb 15, objdump, zstd; Ghidra 12.1.4 + REA 6.5.0 (see §7) |

**All addresses below are for this exact SHA-256.** Heap addresses change
every launch; globals and code addresses do not.

> Trap: `pgrep -n -f 'SimCity 4.exe'` matches Steam's launch wrappers, not
> the game. Use the Wine-side `S:\…` path above.

## 3. What is verified

### 3.1 Native pointer paths (stable across launches)

| Object | Path | Notes |
| --- | --- | --- |
| Clock service | `[0x00B43D5C]` | |
| Date serial | `clock + 0xEC` (u32) | Gregorian day number; decode in `tools/sc4_clock_probe.py`. 1 unit = 1 day |
| Budget object | `[0x00B43D64]` | |
| Funds | `budget + 0x28` (i64) | mirrors at `+0x30` and one UI-side heap copy |
| Tax rate[cat] | `budget + 0x70 + cat*0x80` (f32, percent) | 12 categories |
| Tax base[cat] | `budget + 0xE0 + cat*0x80` (i64) | annual taxable base, rebuilt in place |
| Tax income | `budget + 0x670` (i64) | last month's published total |
| Difficulty-ish index `k` | `[[budget+0x18] + 0x28]` | observed 2; getter `0x0060FB80` |
| Multiplier tables | `*(budget+0x814)`, `*(budget+0x820)`, `*(budget+0x7F8)` | float[3] each |

### 3.2 Simulation date — **verified**

Passed all five gate checks: pause→run→pause, budget changes land exactly on
month rollovers, save→reload preserves the serial, a fresh process resolves
the same path, executable hash recorded.
See `docs/milestones/sc4-clock-distillation-v0.1.md`.

### 3.3 Monthly tax income — **verified, causally tested**

```text
monthly_tax = trunc( Σ_cat base[cat] × mult[k] × rate[cat] / 1200 )
mult = *(budget+0x814) = [1.2, 1.1, 1.0]   (k = 2 in the test city)
```

- `/1200` = percent→fraction (÷100) × one month of an annual amount (÷12).
- Truncation happens **once on the float total**, not per category
  (per-category truncation gives 2498 vs the observed 2500).
- Code: `0x006904C0` computes one category's monthly tax with exactly this
  expression; the base-building loop `0x00691E20` (tail `0x00692036–70`)
  adds the pre-rate integer to `base[cat]` and the taxed amount to a float
  accumulator. `1/1200f` lives at `0x00AB08B8` and has only those two uses.
- `0x00690490` resets all 12 rates to `*(budget+0x820)[k]` = 9 (default rate).
- **Causal test:** writing `rate[0] = 14` (was 7) into memory predicted the
  next four months exactly (4028, 4068, 4068, 4068). Holding all twelve rates
  at 20% then predicted 40+ consecutive months with residual 0.
- Expenses were a constant §2,362/month regardless of tax rate.

Details: `docs/milestones/sc4-tax-distillation-v0.3.md` (and v0.1/v0.2).

### 3.4 OpenGlassBox candidate comparison

The OpenGlassBox sidecar (`sc4-lab/adapters/openglassbox/`) now hosts the
verified tax equation as ruleset `sc4-tax-v0.3`: state lives in OpenGlassBox
city globals (rates/multiplier as exact IEEE bits, bases, funds, expenses),
time advances on its clock, and the protocol gains `budget_set` and
`budget_month` commands. OpenGlassBox's own rule language only adds/removes
integer amounts, so the multiplication itself runs in the C++ helper.

Replaying the 20%-tax ride (81 months, OpenGlassBox commit `fd7d918`):

| Check | Result |
| --- | --- |
| tax income, SC4 inputs each month | 81/81 exact |
| funds, seeded once then open loop with expenses 2,362 | final drift §16 |
| cause of drift | SC4 expenses fell to 2,361 from 2012-11 on |

```bash
bash tools/build_openglassbox_adapter.sh --root /path/to/OpenGlassBox   # pinned fd7d918
python3 tools/sc4_ogb_compare.py ~/.cache/opensc4/dynamic/<ride-dir>
```

## 4. What we observed but have not explained

From the 20%-tax ride (2007-06 → 2010-11 in game, ~42 months):

1. **The tax bases barely respond to a 20% tax.** Over 3.5 game years, base
   sum went 430,838 → 430,223. Category 7 decayed 615 → 270 → 0; everything
   else was frozen to the digit. Either SC4's tax→demand→abandonment path is
   much weaker than expected, demand affects *new* growth rather than
   existing buildings, or these bases are a cache refreshed from something
   that is not changing. **This is the most important open question.**
2. **Measurement artifacts to fix, not SC4 behavior:**
   (Both are avoided by `sc4_ogb_compare.py`, which reads each month three
   game days after the rollover.)
   - Some months show `funds_delta = 0` (so derived "expenses" equals the
     tax). The funds write lands a tick *after* the date flips; the ride tool
     must take the funds delta from a sample a few game-days after rollover.
   - One month (2008-04) read a half-rebuilt base array (residual 182). The
     loop clears and re-accumulates `base[]` in place, so reads must be
     frozen (`SIGSTOP`) or taken away from the rollover.
3. Twelve tax categories but only 9 non-zero bases. Names are unassigned
   (expected R§/R§§/R§§§, C…, I…, but unverified).

## 5. Tools (all in `tools/`)

| Tool | What it does |
| --- | --- |
| `sc4_clock_probe.py` | read date serial + decode |
| `sc4_budget_probe.py` | read funds, tax income, rates, bases |
| `sc4_system_id.py` | `capture` series (clock+budget); `boundaries` correlates date steps with budget changes; `analyze`/`aggregate`/`plan` for paired runs; `self-test` |
| `sc4_dynamic.py` | `dump` (SIGSTOP, raw copy of ~800 MiB writable memory, SIGCONT, ~1 s); `diff` 2 dumps (typed, `--delta`, `--range`) or 3 (sensitivity); `poke` (typed write, read-back, journal, `--restore`); `watch` (gdb hardware watchpoints — see §8) |
| `sc4_ogb_compare.py` | replay a ride through the OpenGlassBox sidecar (`sc4-tax-v0.3` budget slice) and score tax per month + open-loop funds drift |
| `sc4_ride.py` | long run: hold tax rates by memory write, sample every 0.5 s, check the tax equation each month, compressed dump per month |
| `sc4_tax_intervention.py` | call the native tax setter through gdb (older path) |
| `memory_observatory.py` | value scan / hash snapshots / watch (read-only) |
| `sc4_static_candidates.py`, `sc4_evidence_pack.py`, `rea_target_manifest.py` | static leads from strings + objdump, REA preflight |

Raw dumps, samples and disassembly are written to `~/.cache/opensc4/` and
are **never committed** (`tools/check_data_boundary.sh` enforces this).

## 6. Runbook

```bash
cd OpenSC4
pid=$(pgrep -f 'S:\\steamapps\\common\\SimCity 4 Deluxe\\Apps\\SimCity 4.exe')

# sanity: one sample
python3 tools/sc4_system_id.py capture --pid "$pid" --with-clock \
  --experiment-id check --duration 0 --out /tmp/check.jsonl

# dump before/after a month end, then find what moved by a known amount
python3 tools/sc4_dynamic.py dump --pid "$pid" --label a
#   ... let one month pass ...
python3 tools/sc4_dynamic.py dump --pid "$pid" --label b
python3 tools/sc4_dynamic.py diff ~/.cache/opensc4/dynamic/{a,b} \
  --type i32 --delta <known change>

# perturb one input, journaled
python3 tools/sc4_dynamic.py poke --pid "$pid" --field tax_rate:0 --value 14
python3 tools/sc4_dynamic.py poke --pid "$pid" --restore

# long unattended experiment
python3 tools/sc4_ride.py --pid "$pid" --rates 20 --hours 2
#   -> ~/.cache/opensc4/dynamic/ride-*/{months,samples}.jsonl, dumps/*.zst
```

Speeds: at **turtle/llama** ≈ 1 game day per real second; **rhino** is much
faster; **cheetah** can run years in minutes. A 0.5 s sample interval still
catches every month end at rhino.

Static work: `objdump -d -M intel "SimCity 4.exe" > sc4.dis` (2.5 M lines),
then search for constants. The `1/1200` lead came from finding the single
`.rdata` float and its two references.

## 7. REA / Ghidra status

REA 6.5.0 is configured for **Codex** (`~/.codex/config.toml`) with Ghidra
12.1.4 + JDK 21. Last attempt, its Ghidra bridge hit a 330 s timeout
enumerating this PE. Two ways forward: ask REA for **single functions** by
address (`0x006904C0`, `0x00691E20`) rather than whole-program analysis, or
pre-analyze once with Ghidra `analyzeHeadless` and point REA at that project.
To use REA from Claude Code:

```bash
claude mcp add rea \
  -e GHIDRA_INSTALL_DIR=$HOME/.local/opt/opensc4-re-tools/ghidra_12.1.4_PUBLIC \
  -e JAVA_HOME=$HOME/.local/opt/opensc4-re-tools/jdk-21.0.12.1+1 \
  -- npx -y rea-agents@6.5.0 mcp      # needs Node >= 22 on PATH
```

## 8. Known hazards

- **gdb attach under Proton**: the first live `sc4_dynamic.py watch` run
  coincided with Steam and SC4 both exiting (SC4 got SIGTERM 11 s after
  attach, Steam left no log). Cause unproven. Prefer `perf` hardware
  breakpoints, which do not ptrace-stop the process:
  `sudo sysctl kernel.perf_event_paranoid=2` (resets on reboot; Ubuntu
  default 4 blocks it), then
  `perf record -e mem:<addr>/4:w -p <pid> -g`. Not yet wired into the tools.
- Steam/VAC: SC4 is single-player and, to our knowledge, not VAC-enabled.
  Consider Steam offline mode during sessions anyway.
- Heap churn: month ends free and reallocate many objects, so most raw
  diffs are noise. Filter with `--delta`/`--range`, prefer pointer paths
  from module globals, and confirm by perturbation.
- Base array is rebuilt in place at month end — freeze before reading it.

## 9. Roadmap (in priority order)

1. **Fix the ride tool's two artifacts** (funds lag, in-place base rebuild)
   so every month row is trustworthy.
2. **Who builds the bases?** Watch writes to `budget+0xE0` and reads inside
   `0x00691E20`: enumerate the record container it iterates (budget-owned,
   per-building?), the virtual methods it calls for record inputs, and the
   `+0x7F8` table (`[1.0, 0.75, 0.5]`, indexed by a derived value). Goal:
   `base[cat] = Σ_records f(record)` with named inputs.
3. **Demand (RCI).** Find the demand values (static leads: strings in the
   evidence pack; dynamic: values that move when rates change, using a
   3-dump sensitivity diff). Then measure `tax rate → demand`.
4. **Growth/abandonment.** Explain finding §4.1: why bases did not fall
   at 20% tax. Test with a growing city (zoned empty land) where demand
   should matter immediately, and at cheetah speed for longer horizons.
5. **Name the 12 categories** by changing one rate at a time and matching
   the UI's budget panel.
6. **Expenses.** §2,362/month, dropping to §2,361 in 2012-11 (found by
   the OpenGlassBox funds replay); decompose by service (police, fire,
   schools, power, transport) by poking or changing funding sliders.
7. **Verify `k` = difficulty** with a city started on Easy/Medium
   (expect mult 1.2/1.1).
8. Run the OpenGlassBox sidecar **live** inside `sc4_ride.py` (per-month
   comparison as the game runs) and add each new verified rule to its
   ruleset so the funds drift shrinks toward zero.
9. Wire `perf` breakpoints into `sc4_dynamic.py watch` (replace gdb).
10. Port verified rules into `sc4-lab/specifications/` and the Godot
   simulation backend seam (`docs/runbooks/simulation-backend.md`), with
   recorded held-out months as regression fixtures (summaries, not dumps).

## 10. How to help

- Already know SC4 internals (SC4 modding community, gzcom-dll, SC4 Tools,
  the SimCity 4 DLL plugin authors)? Names for the budget record container,
  the category order, or the demand subsystem would save weeks.
- Comfortable in Ghidra/IDA: decompile `0x00691E20` and its virtual calls
  and write down what each record method returns.
- Have a copy of the game: run §6 on a city of your own and send the
  `months.jsonl` (summaries only — never game files or raw dumps).

Evidence rules: one claim per experiment, state the executable hash, keep
raw data private, and mark anything not tested by perturbation as
*candidate*.
