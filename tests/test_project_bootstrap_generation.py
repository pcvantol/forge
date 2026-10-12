"""Real regeneration must ignore checkout/filesystem directory enumeration order."""
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch


class PortableGenerationTests(unittest.TestCase):
    def test_generation_is_identical_under_forward_and_reversed_enumeration(self):
        original=Path.iterdir
        for reverse in [False,True]:
            def enumerated(path):
                return iter(sorted(original(path),reverse=reverse))
            with patch.object(Path,'iterdir',enumerated),patch.object(sys,'argv',['build-portable-validator']):
                runpy.run_path('scripts/build_portable_bootstrap_validator.py',run_name='__main__')
