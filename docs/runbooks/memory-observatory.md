# Runbook: SC4 dynamic memory observatory

## Safety boundary

The observatory is read-only and limited to processes owned by the current
user. It scans readable private mappings, records hashes, or samples explicit
addresses. It does not patch memory, inject code, read another user's process,
or persist raw memory by default.

Use a disposable SC4 city and keep all capture output under `/tmp`. Do not
commit raw dumps, save files, credentials, or unrelated process memory.

## Tool self-test

```sh
python3 tools/memory_observatory.py self-test
```

This creates a synthetic child process, finds a known `u32`, detects its
changed value, and verifies that a hashed snapshot diff reports a changed
region. It is not an SC4 result.

## Inspect a live process

Find the Wine/SC4 PID manually, then inspect readable regions:

```sh
python3 tools/memory_observatory.py --pid "$SC4_PID" maps \
    --out /tmp/sc4-memory-maps.json
```

The output includes address ranges, permissions, sizes, and mapped-file
basenames. It does not include region contents.

## Search a displayed value

Use the displayed value as a candidate search, not a conclusion:

```sh
python3 tools/memory_observatory.py --pid "$SC4_PID" scan \
    --value 1390 --type u32 --max-results 500 \
    --out /tmp/sc4-population-candidates.json
```

Try `i32`, `u64`, `f32`, and `f64` only when the experiment justifies them.
Repeat after a controlled change and intersect candidate addresses. Exclude
executable mappings initially; add `--include-executable` only for a reviewed
code/data investigation.

## Differential snapshots

Snapshots hash selected memory chunks without retaining their bytes:

```sh
python3 tools/memory_observatory.py --pid "$SC4_PID" snapshot \
    --chunk-size 4096 --out /tmp/sc4-memory-before.json

# Advance exactly one named simulation interval or perform one controlled action.

python3 tools/memory_observatory.py --pid "$SC4_PID" snapshot \
    --chunk-size 4096 --out /tmp/sc4-memory-after.json
python3 tools/memory_observatory.py diff \
    --before /tmp/sc4-memory-before.json \
    --after /tmp/sc4-memory-after.json \
    --out /tmp/sc4-memory-diff.json
```

Pause-control snapshots are important: regions that change while paused are
likely rendering, timing, allocation, or unrelated activity. This is a filter,
not proof that a stable region is simulation state.

## Address sampling

After repeated scans identify a candidate address, sample it without a
watchpoint:

```sh
python3 tools/memory_observatory.py --pid "$SC4_PID" watch \
    --address 0xADDRESS --type u32 --interval 0.25 --duration 60 \
    --out /tmp/sc4-address-watch.jsonl
```

Address stability must be checked across reloads and restarts. Absolute
addresses are not portable; record module/region context and rediscover them.

## Validation ladder

1. candidate tracks the displayed value across three changes;
2. candidate stays stable while the UI closes or the simulation pauses;
3. candidate survives save/reload at the same semantic state;
4. candidate is rediscovered after restart or relocation;
5. a writer/access trace or structured save correlation supports the hypothesis;
6. a held-out action disconfirms competing explanations.

Do not label an address as verified after one matching scan. The first target
is treasury or simulation date; then power funding and utility demand.

## Debugger escalation

Hardware watchpoints, `winedbg`, GDB, Frida, and core dumps are separate tools
with higher stability, privacy, and compatibility risks. Use them only after a
candidate address survives the validation ladder, and keep the output local.
The observatory itself does not implement memory writes or code injection.
