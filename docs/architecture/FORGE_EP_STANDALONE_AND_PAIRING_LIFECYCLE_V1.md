# Forge standalone readiness and EP pairing lifecycle V1

**Assignment:** `L2-PRODUCER-STANDALONE-AND-PAIRING-LIFECYCLE-V1-20260930`  
**Owning product:** Forge  
**Subset:** Server-only `FSH-SERVICES`; the parent Console/installer capability remains open.

Forge owns the selected EP peer, the local detach receipt, the readiness
projection and the execution gate. EP owns consumer registration, credential
issuance, authentication and revocation. The deployment owner supplies secure
credential storage and process orchestration. A Forge detach receipt never
asserts EP revocation, service removal or data purge.

## Readiness

The existing authenticated `GET /v1/readiness` retains its peer-required
meaning. Its `ready` field is true only when the declared provider and
scheduler are ready and an exact configured peer passes the real authenticated
EP preflight. An absent, detached, pending, stale, malformed, unreachable,
incorrectly bound or unauthenticated peer keeps it false.

Authenticated `GET /v1/readiness/standalone` is an opt-in projection under
`forge-server-standalone-readiness/v1`. Its `service_ready` and `ready` may be
true only for an initially unpaired instance with an intact identity and
storage, a ready provider and a ready or idle scheduler. `execution_ready` is
always false on this route. `mode` is `STANDALONE` only while the peer has
never been configured; it is `PEER_REQUIRED` for a configured, detached,
pending or invalid peer. A historical detach does not silently switch the
instance into standalone mode. `/v1/readiness` remains the execution-oriented
legacy check; consumers must choose the standalone route explicitly.

The Server's own start requires one existing current-schema instance. It does
not initialize, migrate, discover or choose another deployment. Provider
`VERIFIED` is a separate fact and is never promoted by peer lifecycle work.

## Exact local detach

The packaged CLI is:

```text
forge --data-root ROOT execution-host detach \
  --operation-id OP --instance-id FORGE_INSTANCE \
  --expected-binding-id BINDING --expected-revision REVISION \
  --expected-digest sha256:DIGEST --operator-id OPERATOR
forge --data-root ROOT execution-host detach-status --operation-id OP
```

The same owning service is exposed as authenticated
`POST /v1/execution-host/detach` and
`GET /v1/execution-host/detach/{operation_id}`. The POST body has exactly the
snake-case CLI fields, with `expected_revision` as an integer. The status
route is independent of the POST retry. Successful receipts use
`forge-ep-peer-detach/v1`, bind the request digest, Forge instance, selected
binding ID, exact revision and configuration digest, and declare
`remote_consumer_revoke: NOT_ASSERTED`.

The operation takes the existing lifecycle and runtime writer exclusions and
requires idle dispatch, completed/archived/integration-complete Missions,
reconciled submissions, terminal permits, empty planning queues and idle
operational reset. Blocked or failed work is refused because EP authority may
still need the old binding for product-owned reconciliation. An active writer
or incompatible lifecycle operation is refused. It persists `PREPARED` before
deleting the selected peer.
While `PREPARED`, peer runtime use is fenced as `DETACH_PENDING`. The exact same
operation and request can resume; an altered request with the same operation
ID is refused. Deletion, generation advance and the `COMPLETE` receipt commit
atomically. A terminal replay returns the verified receipt without deleting a
later binding. Its receipt digest is validated on readback and replay.
PRESERVE, RESTORE and PURGE refuse an unfinished detach until its exact
operation is resumed; the existing updater also cannot share the runtime
writer locks with an active detach.

After completion, peer status is `DETACHED`, both readiness routes are false,
and EP-dependent execution is blocked. A new peer must be configured with
`replace=true`, `expected_revision` equal to the detached generation, and
`expected_digest` equal to the detach receipt digest. That configuration gets
the next revision. A first-ever peer uses the existing initial configure
request with `replace=false`. Subsequent replacement of a configured peer
uses its exact current revision and configuration digest. A stale generation,
wrong instance or wrong binding is refused.

## Replacement after EP revocation

The deployment owner first reads the EP consumer and credential status on the
owning EP product. It revokes the old consumer, retains its non-secret
historical revocation evidence, then registers a **new** consumer ID within
the same approved project and repository attachment. EP 2.3.106 does not
reactivate a revoked consumer. Its existing `consumer-register` route is
idempotent for an already-active exact registration. `credential-issue` is
not idempotent: after a lost response, list the new consumer's credentials,
revoke every uncertain issue by exact credential ID, verify inactive status,
then issue again. Ambiguous status blocks recovery.

Only the replacement credential is stored in the approved secure destination.
The Forge configure request binds the unchanged Forge runtime ID, unchanged
EP instance ID, exact new EP consumer ID, project, repository, endpoint and
secure reference. Forge readback is secret-free; preflight must authenticate
that exact consumer and scope against EP before paired readiness is accepted.
The installer retains the old revocation and credential metadata and reviews
the new consumer ID, credential ID/fingerprint, project/repository attachment,
EP instance, Forge binding and configuration revision/digest. A new consumer
or credential generation is not a new product instance.

If an instance was preserved under 2.7.38, its historical receipt remains
bound to those bytes. The deployment owner first invokes the exact installed
2.7.38 product RESTORE on that receipt, then consumes the explicit supported
`2.7.38 -> 2.7.39` schema-39-to-40 update assessment and controller path
before using the new detach contract. The new 2.7.39 RESTORE route does not
relabel a 2.7.38 preserve receipt. The update preserves the runtime,
installation and peer identities and all historical tables while adding the
peer-generation and detach-operation tables. Old peer credentials are never
reactivated by restore or migration.

## Evidence limits

Disposable EP and Forge HTTP/CLI tests can qualify product behavior, replay
and byte preservation. Synthetic provider configuration proves only provider
configuration handling; it is not a live provider login. Foreground server
tests are not LaunchDaemon, Keychain, physical reboot, signer, service-account
or full installer evidence. Forge Platform owns the final choreography and
acceptance within its separate assignment.
