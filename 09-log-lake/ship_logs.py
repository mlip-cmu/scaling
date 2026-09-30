"""Dump all log files of the photo service into Loki, as they are.

Loki stores the raw lines. The only structure that we add is the time of each line and two
labels: the service that wrote it and the host. Start Loki first (`docker compose up -d`).
"""

import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

import photo_data

LOGS = photo_data.path("logs")
TIME_FORMATS = [  # each log file has its own format for the time
    (r"\[(\d\d/\w{3}/\d{4}:\d\d:\d\d:\d\d) \+0000\]", "%d/%b/%Y:%H:%M:%S"),  # nginx access
    (r"^(\d{4}/\d\d/\d\d \d\d:\d\d:\d\d) \[", "%Y/%m/%d %H:%M:%S"),  # nginx error
    (r'"(?:ts|received)": "([^"]+)Z"', "%Y-%m-%dT%H:%M:%S.%f"),  # JSON lines
    (r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3}) ", "%Y-%m-%d %H:%M:%S,%f"),  # Python logging
    (r"^time=(\S+)Z ", "%Y-%m-%dT%H:%M:%S"),  # logfmt
    (r"^(\w{3} [ \d]\d \d\d:\d\d:\d\d) ", "%Y %b %d %H:%M:%S"),  # syslog (no year)
]


def timestamp(line: str) -> int:
    for pattern, fmt in TIME_FORMATS:
        if m := re.search(pattern, line):
            text = m.group(1)
            if fmt.startswith("%Y %b"):  # syslog lines have no year
                text = "2021 " + " ".join(text.split())
            t = datetime.strptime(text, fmt).replace(tzinfo=UTC)
            return int(t.timestamp()) * 10**9 + t.microsecond * 1000
    raise ValueError(f"no time in: {line[:80]}")


def labels(path: Path) -> dict[str, str]:
    name = path.stem  # access-web-1, error-web-1, upload, thumbnailer, deploy, auth, ...
    if path.parent.name == "web":
        kind, host = name.split("-", 1)
        return {"service": "nginx", "file": kind, "host": host}
    return {"service": name}


if __name__ == "__main__":
    loki = httpx.Client(base_url="http://localhost:3100", timeout=60)
    for _ in range(60):  # wait until Loki is ready
        try:
            if loki.get("/ready").text.strip() == "ready":
                break
        except httpx.HTTPError:
            pass
        time.sleep(2)
    total = 0
    for path in sorted(LOGS.rglob("*.*")):
        lines = path.read_text().splitlines()
        values = sorted([str(timestamp(line)), line] for line in lines)
        for i in range(0, len(values), 1000):  # small requests
            stream = {"stream": labels(path), "values": values[i : i + 1000]}
            loki.post("/loki/api/v1/push", json={"streams": [stream]}).raise_for_status()
        total += len(lines)
        print(
            f"{str(path.relative_to(LOGS)):<28} {len(lines):>6} lines  {json.dumps(labels(path))}"
        )
    print(f"{total} lines sent")
    query = {"query": 'sum(count_over_time({service=~".+"}[3d]))', "time": "2021-12-09T00:00:00Z"}
    counts = [-1]
    while True:  # Loki needs a moment until all lines can be queried
        time.sleep(5)
        r = loki.get("/loki/api/v1/query", params=query).json()["data"]["result"]
        counts.append(int(r[0]["value"][1]) if r else 0)
        if counts[-1] == counts[-2] and counts[-1] > 0.95 * total:
            break
    print(f"{counts[-1]} lines in Loki (Loki stores identical lines with the same time only once)")
