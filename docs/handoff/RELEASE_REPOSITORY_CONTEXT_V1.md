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


## Protected implementation and normal finalization

[PR #273](https://github.com/pcvantol/forge/pull/273) protected-merged at
`3846e12c14ba65e3c7754c7a3fb0728b69b72ab6`, reviewed head
`6b912ff700fb37c37afb3f2388ed6fe466028073`.
Independent whole-scope Quality and Security PASS bind that exact head.
Full local validation: 1394 tests, one skip, 706.361s; version/projection PASS.
[Required CI38042154103](https://github.com/pcvantol/forge/actions/runs/38042154103)
passed all retained installed gates, 1394 hosted tests/five skips/1212.987s.
Actual PR checkout `7d407bd3c41b2742c3707f437cd125d9b4be8d13` has the same
`ed0964ba90e9c0a26d3f9d4f5aed914d4b82bf26` tree as reviewed/protected code.
The [actual controller artifact](https://github.com/pcvantol/forge/actions/runs/38042154103/artifacts/11666069770)
was downloaded and verified, with explicit merge-checkout rather than PR-head
provenance. Fresh local runner also passed on actual implementation main.
Real Bash tracing independently establishes 15/15 executable helper lines,
100%; Python changed-product coverage correctly reports no changed files.

This nonempty NO_BUMP finalization records the implementation evidence in
[the selected delivery record](../qualification/forge-release-repository-context-selected-delivery-2026-10-10.json).
Finalization approval/protected merge and fresh exact-final-main controller
qualification remain open until their actual readbacks. No old installed PASS
is substituted for that execution. Candidate TDE38042154107 was CANCELLED;
no policy PASS is claimed. Correction rounds consumed0/max3/remaining3.
