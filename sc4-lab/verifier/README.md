# Independent verifier

The verifier will compare normalized observations from both adapters. Acceptance
rules and tolerances must be reviewed and fixed before candidate runs. It must
not load candidate code that can rewrite expected results or test definitions.

The command-line implementation consumes JSON observation records and a
separate tolerance policy:

```sh
python3 sc4-lab/verifier/compare.py \
    --reference /path/to/reference-observation.json \
    --candidate /path/to/candidate-observation.json \
    --tolerances sc4-lab/verifier/tolerances.v1.json \
    --report /tmp/opensc4-comparison.json
```

`unsupported` reference metrics are reported but never counted as passing.
Observed metrics require a fixed rule; missing rules are verifier failures, not
automatic defaults. Reports are generated outside the repository unless they
contain only synthetic data.
