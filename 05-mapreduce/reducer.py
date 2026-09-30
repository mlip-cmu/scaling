#!/usr/bin/env python3
"""Reduce: lines "key<TAB>count", sorted by key -> "key<TAB>sum" (also used as combiner)."""

import sys

current, total = None, 0
for line in sys.stdin:
    key, count = line.rstrip("\n").split("\t")
    if key != current:
        if current is not None:
            print(f"{current}\t{total}")
        current, total = key, 0
    total += int(count)
if current is not None:
    print(f"{current}\t{total}")
