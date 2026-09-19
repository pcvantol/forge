# Autonomous Mission vertical slice: implementation and qualification scope

This delivery adds a packaged `forge mission` entrypoint for read-only input
inspection, canonical Business and Architecture decisions, admission of one
approved Mission, one foreground start, status, controlled stop, and reopen of
the same execution. It composes the existing governance repository, Mission
Intake, installed dynamic runtime, Execution Loop, Runtime Service, and EP HTTP
adapter. The CLI does not decide Action content or criterion completion.
The approved input binds a GitHub owner/repository to the installed EP repository
identity. On first start, Forge reads that repository's current default-branch
commit through the configured GitHub identity and builds initial Repository
Truth from that readback. The supplied revision must match; caller-provided
evidence rows and timestamps are not promoted to runtime authority.
The approved Mission constraints carry one EP-issued, Mission-scoped merge
delegation reference and, for host-control criteria, the exact delivery
validation request `ep-delivery-control-validation:1`. Forge transports those
immutable constraints in the accepted Producer provenance. The installed EP
must declare control publication, delivery validation, and bounded merge
capabilities before the foreground command starts. A read-only
input inspection checks the reference syntax; it does not assert that EP has
reserved or activated the grant. Before the first start and at each new-work
boundary, Forge reads the authenticated EP grant and requires an active,
unexpired exact Mission/revision, repository, GitHub.com origin, protected
`main`, and delivery role binding. The initial GitHub head is read from
`github.com/main`. If that grant expires or is revoked after EP accepted a run,
a reopened controller may read and assess only that persisted run. It stops
before a successor plan or submission and records a blocked Mission when the
assessment remains partial. Temporary status loss and recoverable repository
origin drift stop the controller without recording a permanent grant block.
EP rejects new submissions and merges without an active grant.

The functional evidence source is an EP-owned, immutable terminal artifact
containing the actual candidate-bound validation-control execution record.
Forge accepts only controls named in the approved assessment contract and
bound to the same Mission, Action, submission, run, candidate, and delivery.
An executed passing behavioral test with nonzero discovered tests can support
its declared criterion. A missing, skipped, empty, contradictory, or unrelated
control cannot. Repository JSON remains available for structural assertions.
For `current_revision`, the control must have run on the accepted delivery SHA;
candidate-only controls remain historical evidence. EP publishes the actual
post-delivery execution record and Forge retains the original candidate and
delivery identities separately.

The bounded qualification target is a dedicated, disposable Python package
for this slice. Its two observable criteria are: (1) the public parser rejects
an invalid input with a nonzero exit and stable error; (2) the public parser
accepts a valid input and emits the documented result. The independent test
consumer invokes the installed package entrypoint; EP owns the validation
control identity and output, and Forge owns their criterion interpretation.
The target is never an existing user repository. Its exact remote identity,
test consumer, EP registration, isolated Forge/EP data roots, and provider
budget must be recorded before an external qualification run. Until then only
source and isolated local fixture tests are authorized.

Forge owns the command, governance and intake composition, foreground
controller, planning continuation, and criterion observer/evaluator. EP owns
actual validation and authenticated publication of its records. A qualifying
run starts once from the packaged CLI and reaches a terminal Mission result,
including partial assessment and a newly derived successor when needed,
without a driver mutating state between Actions. Single-Action completion is
also valid when it proves every approved requirement. Publication, installed
readback, protected delivery, and safe installation are separate release gates.

This scope never allocates production Mission 3, resets production CENTRAL,
or treats the previous Mission-3 preflight as successful.
