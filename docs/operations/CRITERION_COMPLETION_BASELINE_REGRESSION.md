# Criterion completion baseline regression

The new correction assignment is separate from the rejected Mission-3
preflight in PR #148. The earlier acceptance remains NIET_GEHAALD and the
production Mission remains NIET_GESTART.

The standalone `scripts/regress_criterion_completion.py` exercises the public
installed runtime factory in separate processes against an isolated persistent
synthetic store. It supplies external identity, Codex subprocess transport and
canonical typed Host evidence fixtures. The real provider parser, admission,
durable planner, evidence-binding function, completion evaluator, runner and
storage are unchanged. It is not live provider or EP HTTP qualification.

Against the non-editable published Forge 2.7.24 wheel, Action A supplies only
K1 evidence. Both K1 and K2 become PROVEN; the runner completes the Mission;
there is one initial planner invocation and zero successor invocations. The
three desired-behavior assertions fail with process exit 1. This demonstrates
the full binding → evaluation → runner → absent-planning chain.

Exact baseline release source: `d5461a345222c3e9c45661fbab0668760264ff0c`.
Wheel SHA-256: `203382514160616d6236bea6f177655e316d4318fe14b9c6871406466f7fcabd`.
The four root-cause source files also match source main
`04bb525cae0043bac87ca605b0ee83bc1e1bef82`.
Artifact identity was checked against the installed wheel and retained
publication/RELEASE_COMPLETE evidence; this is not a fresh registry download.

Run the script with the isolated installed wheel interpreter, `-I`, and a fresh
`--output-dir`. Optional `--wheel` and `--publication-receipt` arguments bind
exact baseline bytes. The normal command prints a sanitized summary; raw
receipts, process output and local paths stay in the private output directory.
Never use a production root. Synthetic IDs are a separate fixture namespace.

Earlier generic A→B tests supplied their own criterion-association callback;
therefore they did not qualify the normal installed binding function. Their
loop assertions remain useful but cannot replace this composition regression.
This baseline test records the defect, not a corrected-product PASS.
