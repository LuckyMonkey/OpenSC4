# Milestone: local reference capture D2

## Outcome

The lab can now capture local save metadata and user-owned process metadata
around a controlled SC4 action without copying game bytes into the repository.

## Delivered

- `tools/reference_capture.py snapshot` records file size, timestamps, whole-file
  hashes, and fixed-size chunk hashes.
- `diff` reports changed chunk ranges and size/hash changes without emitting
  raw bytes.
- `watch` records a JSONL timeline when a save hash changes.
- Optional `--pid --include-maps` records selected process status and mapped
  region metadata for the current user only.
- Raw `/proc/PID/mem` reads and raw memory dumps are intentionally not part of
  the default tool.

## Test evidence

The tool was exercised on synthetic repository JSON files and a user-owned
shell process:

- five capture commands returned `REFERENCE CAPTURE PASS`;
- changed-range output reported `raw_bytes_recorded: false`;
- process output reported `raw_memory_read: false` and mapped-region metadata;
- the zero-duration watcher emitted one initial JSONL record.

These are tool tests, not SC4 observations.

## First SC4 experiment

When a local city save and live SC4 process are available:

1. choose a disposable test city and record its version/provenance locally;
2. capture before state;
3. perform exactly one action and save;
4. capture after state and compute the changed-range report;
5. repeat the same action from the same starting save;
6. correlate stable ranges with parser-visible values and UI/stat changes;
7. write a hypothesis only after repeated evidence.

No reference observation is accepted from changed offsets alone. The current
workspace has no live SC4 process or `.sc4` save available for this run.
