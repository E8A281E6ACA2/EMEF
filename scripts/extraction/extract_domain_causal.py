#!/usr/bin/env python3
import runpy
import sys
from pathlib import Path

target = Path(__file__).resolve().parents[2] / "src/core/extraction/four_stage/pipeline/extract_domain_causal.py"
sys.argv = [str(target)] + sys.argv[1:]
runpy.run_path(str(target), run_name="__main__")
