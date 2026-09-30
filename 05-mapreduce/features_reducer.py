#!/usr/bin/env python3
"""Reduce: all views of one photo -> features for a model: views, viewers, share from the app."""

import sys
from itertools import groupby

rows = (line.rstrip("\n").split("\t") for line in sys.stdin)
for path, views in groupby(rows, key=lambda r: r[0]):
    views = list(views)
    viewers = len({v[1] for v in views})
    app = sum(int(v[2]) for v in views) / len(views)
    print(f"{path}\t{len(views)}\t{viewers}\t{app:.2f}")
