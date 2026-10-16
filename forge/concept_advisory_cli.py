"""Explicit owner setup and private service CLI; no ambient credential fallback."""
import argparse
import json
import io
import os
import select
import sqlite3
import sys
import time
from pathlib import Path
from .concept_advisory_contract import CONTRACT
from .concept_advisory_grant import ConceptAdvisoryGrant
from .concept_advisory_service import ConceptAdvisoryService, provider_profile
from .project_bootstrap.schema import load_json
from .workspace_review_grant import _private_bytes


def publish_cli(grant, authorization, audience, document, *, chunk_bytes=4096):
    if type(chunk_bytes) is not int or not 1 <= chunk_bytes <= 65536:
        raise ValueError("finite publication chunk required")
    raw = (json.dumps(document, sort_keys=True)+'\n').encode()
    if isinstance(sys.stdout, io.StringIO):
        # An in-memory caller buffer cannot block waiting on a consumer.
        with grant.publication(authorization, audience, document):
            sys.stdout.write(raw.decode())
        return
    fd = sys.stdout.fileno(); blocking = os.get_blocking(fd)
    deadline = time.monotonic()+5; offset = 0
    try:
        os.set_blocking(fd, False)
        while offset < len(raw):
            if time.monotonic() >= deadline:
                raise TimeoutError('bounded CLI publication deadline')
            if not select.select([], [fd], [], min(0.1, max(0, deadline-time.monotonic())))[1]:
                continue
            try:
                with grant.publication(authorization, audience, document, deadline=deadline):
                    if time.monotonic() >= deadline:
                        raise TimeoutError('bounded CLI publication deadline')
                    sent = os.write(fd, raw[offset:offset+chunk_bytes])
            except BlockingIOError:
                continue
            if sent <= 0:
                raise OSError('CLI publication interrupted')
            offset += sent
    finally:
        os.set_blocking(fd, blocking)

def main(argv=None):
    parser = argparse.ArgumentParser(prog='forge-concept-advisory')
    parser.add_argument('--data-root', required=True)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('init')
    profile = sub.add_parser('provider-profile'); profile.add_argument('--provider-id', required=True)
    issue = sub.add_parser('issue')
    for key in ('principal-id', 'audience', 'provider-id', 'transfer-policy-digest', 'expires-at', 'token-file'):
        issue.add_argument('--'+key, required=True)
    for key in ('dossier-id', 'conversation-id', 'permission'):
        issue.add_argument('--'+key, action='append', required=True)
    issue.add_argument('--maximum-turns', type=int, required=True); issue.add_argument('--maximum-tokens', type=int, required=True); issue.add_argument('--maximum-seconds', type=int, required=True)
    revoke = sub.add_parser('revoke'); revoke.add_argument('--grant-id', required=True)
    for action in ('capability', 'submit', 'history', 'intent'):
        item = sub.add_parser(action); item.add_argument('--token-file', required=True); item.add_argument('--audience', required=True)
        if action in ('history', 'intent'):
            item.add_argument('--dossier-id', required=True); item.add_argument('--conversation-id', required=True)
        if action == 'intent': item.add_argument('--operation-id', required=True)
        if action == 'submit': item.add_argument('--request-file', required=True)
    args = parser.parse_args(argv)
    try:
        from .server_runtime import existing_instance
        instance = existing_instance(args.data_root); grant = ConceptAdvisoryGrant(instance.data_root, instance.instance_id)
        if args.action == 'init':
            from .runtime.bootstrap import RuntimeBootstrap
            from .operator_identity import InstallationOperatorService, MacOSGeneratedUIDIdentityAdapter
            from ._version import canonical_version
            with RuntimeBootstrap(data_root=instance.data_root, forge_version=canonical_version()).open() as db:
                owner = InstallationOperatorService(db, MacOSGeneratedUIDIdentityAdapter().resolve)
                if not db._connection.execute('SELECT 1 FROM installation_operator_binding').fetchone(): owner.first_bind()
                else: owner.context()
            grant.initialize(); document = {'contract_version': CONTRACT, 'state': 'PRIVATE_CONCEPT_ADVICE_INITIALIZED'}
        elif args.action == 'provider-profile': document = provider_profile(instance.data_root, args.provider_id)
        elif args.action == 'revoke': document = grant.revoke(args.grant_id)
        elif args.action == 'issue':
            document = grant.issue(principal_id=args.principal_id, audience=args.audience, dossier_ids=args.dossier_id,
                                   conversation_ids=args.conversation_id, permissions=args.permission, maximum_turns=args.maximum_turns,
                                   maximum_tokens=args.maximum_tokens, maximum_seconds=args.maximum_seconds, provider_id=args.provider_id, transfer_policy_digest=args.transfer_policy_digest,
                                   expires_at=args.expires_at, token_path=args.token_file)
        else:
            token = _private_bytes(Path(args.token_file))
            if len(token) > 256: raise ValueError('finite token required')
            authorization = 'Bearer '+token.decode().strip(); service = ConceptAdvisoryService(grant)
            if args.action == 'capability': document = service.capability(authorization, args.audience)
            elif args.action == 'submit': document = service.submit(authorization, args.audience, load_json(_private_bytes(Path(args.request_file))))
            else: document = service.read(authorization, args.audience, args.dossier_id, args.conversation_id, args.operation_id if args.action == 'intent' else None)
        if args.action in ('capability', 'submit', 'history', 'intent'):
            try:
                publish_cli(grant, authorization, args.audience, document)
            except (OSError, ValueError, RuntimeError, PermissionError, sqlite3.Error):
                # Never append a secondary blocking write after partial publication.
                return 1
        else:
            print(json.dumps(document, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, PermissionError, sqlite3.Error):
        print(json.dumps({'contract_version': CONTRACT, 'error': {'code': 'CONCEPT_CLI_UNAVAILABLE'}})); return 1


if __name__ == '__main__': raise SystemExit(main())
