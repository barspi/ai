#!/usr/bin/env python3
"""Rebuilds sample-lineage.svg from sample-graph.json with the skill's own builder (build.py). Nothing is drawn here.

usage: python3 make_sample.py [out.svg]      (default: sample-lineage.svg next to this file)
then:  python3 ../check_diag.py sample-lineage.svg      (0 failures)
"""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'sample-lineage.svg')
sys.exit(subprocess.call([sys.executable, os.path.join(HERE, '..', 'build.py'), os.path.join(HERE, 'sample-graph.json'), out]))
