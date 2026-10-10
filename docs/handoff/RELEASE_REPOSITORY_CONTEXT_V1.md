# Forge release repository context V1

Assignment `L3-RELEASE-REPOSITORY-CONTEXT-V1-20261010`, L3 r46/plan1.
Selected scope: the existing production release controller's repository binding,
immutable receipt retention and directly affected recovery readback.
Base `d824d729e12e6aafed7b38f7f99cdffd6ef89f34`.

## Owning caller matrix

| Production stage | GitHub calls | Repository and host | Existing identity |
| --- | --- | --- | --- |
| QUALIFIED retention | view, download, create | validated owning pcvantol/forge, github.com | version/tag/source/QUALIFIED bytes |
| Before PyPI | download | same explicit binding | original operation and exact QUALIFIED bytes |
| PUBLISHED retention | view assets/source, upload if absent, download/cmp | same explicit binding from non-Git runner directory | original operation/source/tag/version/digests/publication receipt |
| Cleanup and COMPLETE | view, download, edit; receipt upload/readback | same explicit binding | exact PUBLISHED/pending/COMPLETE bytes and cleanup history |

`release_github_context.sh` refuses absent/wrong owning repository or server URL
before the owning step changes local receipts or calls GitHub. It binds the
fully qualified `github.com/pcvantol/forge` repository and host independently of
cwd, `GH_REPO` and ambient `GH_HOST`. Existing reconciliation already supplies
explicit repository context and is unchanged.

Receipt absence is established through successful asset metadata readback.
A failed existing receipt download cannot be interpreted as absence. A new
upload is followed by exact download/cmp, and an uncertain upload fails the
job. A new runner resumes the same retained operation; existing conflicting
bytes are never overwritten. Pending recovery also refuses failed readback
instead of ignoring a retained cleanup failure.

## Qualification and delivery boundary

The owning unittest discovery executes the delivered workflow shell with real
`release_operation.py` state transitions and real filesystem cleanup. Only the
external GitHub boundary is a local fixture. Tests cover non-Git directories,
a different real Git repository, hostile ambient context, invalid owning context,
exact receipt replay, source/version/operation/digest/receipt conflicts,
failed download, uncertain upload/restart and pending recovery.
The delivered qualification runner also restores the missing explicit binding
in the actual helper and requires the same two positive tests to fail with the
original Git-context error and wrong-repository error.
CI retains logs and a source/tree/file-digest-bound qualification receipt.
Fresh exact-final-main controller execution is required before terminal handoff.

Version decision: **NO_BUMP / 2.12.2**. This is repository release-controller
maintenance, outside the packaged Forge product; no `forge/`, package metadata,
API/runtime/schema or package-data bytes change. It grants no new publication
and does not create replacement distributions under the existing version.
Executable production Python is unchanged; changed shell/YAML behavior is
qualified through execution, with no invented Python linecoverage. All existing
required validation/installed gates remain applicable and unchanged.

R43/r44 remain CLOSED3/3; r45 remains CLOSED2/3. The new assignment admits
consumed0/max3/remaining3 formal integrated corrections after its first complete
independent Quality/Security review. Historical original release run38024005735
remains FAIL and reconciliation38026475188 remains RELEASE_COMPLETE; no old
release assets, tags, receipts or installed qualification are rewritten.
L1/L4 checkouts, pins, credentials and test resources are unchanged.
