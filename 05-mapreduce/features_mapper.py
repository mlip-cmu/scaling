#!/usr/bin/env python3
"""Map: each photo view -> "path<TAB>user<TAB>1 if the view came from the mobile app, else 0"."""

import sys

for line in sys.stdin:
    f = line.split()
    if len(f) > 8 and f[5] == '"GET' and f[6].startswith("/st/") and f[8] in ("200", "304"):
        print(f"{f[6]}\t{f[2]}\t{int('PhotosApp' in line)}")
