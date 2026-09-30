"""Follow the view counts of the 3 most viewed photos while the logs are replayed.

After 40 s, the speed layer crashes and restarts. Start the system first
(`docker compose up -d --build`), then run this script at once.
"""

import collections
import subprocess
import sys
import time

import httpx
import pandas as pd

import photo_data
from components import END, is_view, parse

CRASH_AT = float(sys.argv[1]) if len(sys.argv) > 1 else 40

views = [
    e
    for f in photo_data.access_logs()
    for line in f.read_text().splitlines()
    if is_view(e := parse(f.stem.removeprefix("access-"), line))
]
by_photo = collections.defaultdict(list)
for e in views:
    by_photo[e["path"]].append((e["server"], e["time"]))
photo_id = dict(zip(photo_data.photos().path, photo_data.photos().photo_id, strict=True))
top = sorted(by_photo, key=lambda p: -len(by_photo[p]))[:3]
ids = [int(photo_id[p]) for p in top]


def truth(path: str, latest: dict[str, str]) -> int:
    """The true number of views that the system has seen: the events up to the time that the
    speed layer has reached on each server's partition."""
    return sum(1 for server, t in by_photo[path] if t <= latest.get(server, ""))


api = httpx.Client(base_url="http://localhost:8000", timeout=5)
while True:
    try:
        api.get("/status").raise_for_status()
        break
    except httpx.HTTPError:
        time.sleep(1)

print("For each photo: views = batch result + speed layer (true number in parentheses)\n")
print(f"{'s':>4}  {'events up to':<17} {'batch until':<14}" + "".join(f"{i:>22}" for i in ids))
rows, start, crashed = [], time.monotonic(), False
while True:
    s = api.get("/status").json()
    latest = s["speed_latest"]
    counts = [api.get(f"/photos/{i}/views").json() for i in ids]
    wrong = [c["views"] - truth(p, latest) for c, p in zip(counts, top, strict=True)]
    now = min(latest.values()) if latest else "-"
    cells = "".join(
        f"{c['batch']:>7} + {c['speed']:>4} = {c['views']:>3} ({c['views'] - w:>3})"
        for c, w in zip(counts, wrong, strict=True)
    )
    elapsed = time.monotonic() - start
    print(
        f"{elapsed:>4.0f}  {now[:16]:<17} {(s['batch_until'] or '-')[:13]:<14}{cells}", flush=True
    )
    rows.append(
        {"s": round(elapsed), "events_up_to": now, "batch_until": s["batch_until"]}
        | {f"views_{i}": c["views"] for i, c in zip(ids, counts, strict=True)}
        | {f"error_{i}": w for i, w in zip(ids, wrong, strict=True)}
    )
    if not crashed and elapsed > CRASH_AT:
        crashed = True
        print("      the speed layer crashes (kill) and restarts", flush=True)
        subprocess.run(["docker", "compose", "kill", "speed-layer"], capture_output=True)
        subprocess.run(["docker", "compose", "up", "-d", "speed-layer"], capture_output=True)
    if s["batch_until"] == END and now == END:
        break
    time.sleep(6)

pd.DataFrame(rows).to_csv("out/timeline.csv", index=False)
sample = sorted(by_photo)[:300]
exact = sum(
    api.get(f"/photos/{photo_id[p]}/views").json()["views"] == len(by_photo[p]) for p in sample
)
print(
    f"\nAt the end, the batch layer covers all events: {exact} of {len(sample)} photos (a sample)"
)
print("have exactly the true number of views.")
