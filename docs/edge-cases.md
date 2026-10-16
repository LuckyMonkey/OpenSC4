# Edge-case matrix

Use this list to turn failures into small, repeatable tests. A row is complete
when the expected behavior is documented and the harness can detect regressions.

| Area | Case | Expected result | Current state |
| --- | --- | --- | --- |
| Boot | missing `user://config.ini` | prompt for a local SC4 folder | implemented, manually verify |
| Boot | folder missing one DAT | clear error identifying the file | needs test |
| Boot | invalid/non-directory path | reject without loader thread leak | partially implemented |
| Region | empty region | render empty grid without selecting a city | needs test |
| Region | single click during boot transition | does not fall through to a city tile | fixed, needs visual retest |
| Region | 16:9/21:9/32:9 resize | legacy UI remains bottom-left and clipped correctly | implemented, needs matrix |
| City | missing save | quit with a useful error | implemented |
| City | empty city | terrain and UI load with no occupants | needs save fixture |
| City | no props/flora | no empty MultiMesh churn or errors | implemented path, needs fixture |
| City | no water | water setup remains valid | needs fixture |
| City | no power lines/pipes | log absence and continue | implemented |
| City | missing model TGI | skip only that occupant and continue | implemented, needs fixture |
| City | invalid sprite rectangle | skip sprite and report source TGI | implemented |
| City | empty heightmap | return zero altitude safely | hardened |
| Renderer | zero terrain blend weight | avoid NaN/black terrain | hardened |
| Renderer | fast water mode | stable opaque water with lower shader cost | implemented, benchmark pending |
| Camera | repeated zoom/rotation | no stale model variant or crash | sweep passes |
| Camera | free orbit | restore iso camera transform on exit | implemented, visual review pending |
| Save | wrong backend/ruleset version | refuse with actionable migration error | not implemented |
| Simulation | same input, same seed | exact replay where deterministic | not implemented |
| Simulation | stochastic output | compare repeated-run distributions | not implemented |
