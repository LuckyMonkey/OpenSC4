# SC4 simulation-date distillation v0.1

Date: 2026-10-17  
Status: runtime candidate; save/reload and restart promotion checks remain.

## Result

The read-only `tools/sc4_clock_probe.py` now resolves a live simulation-date
candidate from the running SC4 process without screenshots or process-memory
writes.

The candidate is the scalar returned by the embedded date object's native
vtable method. Static inspection of the exact SC4 executable established this
path:

```text
clock service global 0x00b43d5c
  └─ vtable +0x1c → embedded date object at this+0xf0
       └─ date vtable +0x68 → 0x0091297e → return [this-4]
            └─ scalar storage = clock service +0xec
```

The calendar conversion helper at `0x00912789` was reconstructed from its
integer instructions. It uses the constants `0x1a431f`, `0x23ab1`, `0x5b5`,
and `0x99`, including the native month rollover and day quotient behavior.
The probe implements that conversion directly and labels the result as a
runtime candidate rather than claiming full clock equivalence.

## Live observation

Target executable SHA-256:

```text
f512a405c1e3f0dc82b784d5d9619f4751f03d0905d9d6b94cd528f1d4be1153
```

A live city session produced three identical read-only observations over four
diagnostic seconds:

| Metric | Observed value |
| --- | ---: |
| Native date serial | `2471643` |
| Simulation year | `2055` |
| Simulation month | `1` |
| Simulation day | `10` |

The process was not altered and no save was changed. The unchanged serial is
consistent with a paused/non-advancing simulation interval, but it does not
yet establish the game's tick rate or budget-update boundary.

## Reproduce locally

Find the running process and capture one or more samples:

```bash
cd /home/freezer/OpenSC4
pid=$(pgrep -n -f 'S:\\steamapps\\common\\SimCity 4 Deluxe\\Apps\\SimCity 4.exe')
python3 tools/sc4_clock_probe.py \
  --pid "$pid" \
  --duration 60 \
  --interval 2 \
  --out /tmp/opensc4-clock-observation.jsonl
```

The output contains the serial, decoded calendar date, image base, session
object addresses, static resolution evidence, and explicit raw-byte/write
boundaries. Keep live output outside Git.

The conversion-only smoke check is:

```bash
python3 tools/sc4_clock_probe.py --self-test
```

## What is established

- The executable contains a clock service global used by multiple native
  routines.
- Its vtable returns an embedded date object.
- The date object's `+0x68` method returns the scalar stored immediately
  before the embedded object.
- The native date helper's integer conversion can be reproduced exactly for
  the observed positive serial range.
- The same session yielded a stable, structured live value without UI parsing.

## What is not established

- The simulation tick or wall-clock-to-simulation-speed mapping.
- Whether the date serial advances once per simulation day, month, or another
  internal boundary under each speed setting.
- Save/reload preservation of the serial and object resolution.
- Restart rediscovery across a new process.
- Whether budget/tax writers run on the same boundary as the date serial.

## Promotion gate

Promote this from runtime candidate to verified simulation-date telemetry only
after the same serial/date relationship survives:

1. a controlled pause → run → pause sequence;
2. a save followed by reload of a disposable city;
3. a fresh SC4 process session;
4. one observed date transition correlated with the budget probe; and
5. an independently recorded executable hash.

The next experiment should use the current read-only clock and budget probes
together: `tools/sc4_system_id.py capture --with-clock` followed by
`tools/sc4_system_id.py boundaries` checks items 1 and 4 in one run (see
`docs/runbooks/sc4-system-identification.md`, "Date-boundary promotion run"). Do not add a simulation tick field to the shared observation schema
until a separate native tick/update counter is found.
