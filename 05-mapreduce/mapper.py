#!/usr/bin/env python3
"""Map: each line of an nginx access log -> "path<TAB>1" for each view of a photo."""

import os
import sys

# For the demo of a failed task: the first attempt of this map task crashes.
attempt = os.environ.get("mapreduce_task_attempt_id", "")
if os.environ.get("FAIL_TASK") and attempt.endswith(f"_m_{os.environ['FAIL_TASK']}_0"):
    sys.exit(f"simulated crash in {attempt}")

for line in sys.stdin:
    f = line.split()
    # 192.0.2.7 - ckaestne [06/Dec/2021:02:49:12 +0000] "GET /st/u211/1U6uFl47Fy.jpg HTTP/1.1" 200
    if len(f) > 8 and f[5] == '"GET' and f[6].startswith("/st/") and f[8] in ("200", "304"):
        print(f"{f[6]}\t1")
