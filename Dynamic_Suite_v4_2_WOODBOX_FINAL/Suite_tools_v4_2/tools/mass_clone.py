#!/usr/bin/env python3
import runpy, pathlib, sys
here = pathlib.Path(__file__).resolve().parent
sys.argv[0] = str(here/'clone.py')
runpy.run_path(str(here/'clone.py'), run_name='__main__')
