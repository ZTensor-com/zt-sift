"""Reuse immutable audit fixtures; save model comparisons in this directory."""
import importlib.util
from pathlib import Path
import sys

source=Path(__file__).resolve().parent.parent/'json_fix_validation/validate.py'
spec=importlib.util.spec_from_file_location('model_audit',source)
audit=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
audit.__file__=__file__
if __name__=='__main__':
    audit.main()
