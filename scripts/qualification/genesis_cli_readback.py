"""Finite private file sink for actual installed CLI output larger than log limits."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys


def main():
    path=Path(sys.argv[1]);arguments=sys.argv[2:];old=sys.stdout
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    exit_code=0
    with os.fdopen(fd,'w',encoding='utf-8') as output:
        try:
            sys.stdout=output;sys.argv=['forge-genesis-bootstrap',*arguments]
            try:
                runpy.run_module('forge.genesis_bootstrap_cli',run_name='__main__')
            except SystemExit as result:
                exit_code=result.code
        finally:
            sys.stdout=old
    size=path.stat().st_size
    if size>2*1024*1024:
        raise ValueError('finite private CLI result exceeded')
    raw=path.read_bytes()
    print(json.dumps({'exit_code':exit_code,'bytes':size,'sha256':hashlib.sha256(raw).hexdigest()}))
    return exit_code


if __name__=='__main__':
    raise SystemExit(main())
