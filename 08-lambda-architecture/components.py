"""The lambda architecture for the view counts of photos.

- log-shipper: replays the logs of the 4 web servers into the topic `view_logs`
- archiver:    stores all events in the data store (Parquet files, append only)
- batch-layer: recomputes the exact view counts from all stored events, regularly
- speed-layer: updates the view counts incrementally for each new event
- serving:     answers requests with the last batch result plus the speed-layer updates

Run one with `python components.py <name>` (the containers in compose.yaml do this).
"""

import collections
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import redis

import common
import photo_data
from common import consumer, ensure_topics, log, producer, send

TOPIC, PARTITIONS = "view_logs", 4
LAKE = Path(os.environ.get("LAKE", "out/lake"))
END = "2021-12-09T00:00:00Z"  # the end of the logs
LINE = re.compile(r'^(\S+) - (\S+) \[([^\]]+)\] "(\S+) (\S+) [^"]*" (\d{3}) (\d+)')


def parse(server: str, line: str) -> dict:
    ip, user, t, method, path, status, size = LINE.match(line).groups()
    t = datetime.strptime(t, "%d/%b/%Y:%H:%M:%S %z").strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "type": "request",
        "server": server,
        "time": t,
        "user": user,
        "method": method,
        "path": path,
        "status": int(status),
    }


def is_view(e: dict) -> bool:
    return e["method"] == "GET" and e["path"].startswith("/st/") and e["status"] in (200, 304)


def store() -> redis.Redis:
    return redis.Redis(host=os.environ.get("REDIS_HOST", "localhost"), decode_responses=True)


def log_shipper():
    ensure_topics({TOPIC: PARTITIONS})
    speedup = float(os.environ.get("SPEEDUP", 2880))  # 3 days in 90 s
    events = []
    for f in photo_data.access_logs():
        server = f.stem.removeprefix("access-")
        events += [parse(server, line) for line in f.read_text().splitlines()]
    events.sort(key=lambda e: e["time"])
    p = producer()
    time.sleep(float(os.environ.get("START_DELAY", 10)))
    log(f"shipping {len(events)} log lines of {PARTITIONS} servers")
    start, t0 = pd.Timestamp(events[0]["time"]), time.monotonic()
    for i, e in enumerate(events):
        wait = (pd.Timestamp(e["time"]) - start).total_seconds() / speedup - (time.monotonic() - t0)
        if wait > 0:
            time.sleep(wait)
        send(p, TOPIC, e["server"], e, partition=int(e["server"][-1]) - 1)  # one per server
        if i % 10_000 == 0:
            log(f"{i} lines sent, now at {e['time']}")
    for s in sorted({e["server"] for e in events}):  # a watermark: no older events will come
        send(p, TOPIC, s, {"type": "watermark", "server": s, "time": END}, int(s[-1]) - 1)
    p.flush()
    log("done")
    while True:
        time.sleep(3600)


def archiver():
    """Append the events to Parquet files, one file per partition and small batch."""
    (LAKE / "views").mkdir(parents=True, exist_ok=True)
    conf = {"enable.auto.commit": False, "enable.auto.offset.store": True}
    c = consumer("archiver", [TOPIC], **conf)
    buffer: dict[int, list] = collections.defaultdict(list)
    last = time.monotonic()
    while True:
        msg = c.poll(0.5)
        if msg is not None and not msg.error():
            buffer[msg.partition()].append((msg.offset(), json.loads(msg.value())))
        if buffer and time.monotonic() - last > 2:
            for part, rows in buffer.items():
                df = pd.DataFrame([e for _, e in rows]).assign(partition=part)
                # the name depends on the first offset: a batch written again replaces the file
                df.to_parquet(LAKE / "views" / f"part-{part}-{rows[0][0]:08d}.parquet")
            c.commit(asynchronous=False)  # only after the files are written
            buffer.clear()
            last = time.monotonic()


def batch_layer():
    """Recompute everything from all stored events, up to the last complete hour."""
    import duckdb

    r = store()
    files = str(LAKE / "views" / "*.parquet")
    runs = 0
    while True:
        time.sleep(float(os.environ.get("BATCH_EVERY", 20)))
        if not list((LAKE / "views").glob("*.parquet")):
            continue
        start = time.monotonic()
        con = duckdb.connect()
        latest = con.execute(
            f"SELECT count(*), min(t) FROM (SELECT server, max(time) AS t "
            f"FROM read_parquet('{files}') GROUP BY server)"
        ).fetchone()
        if latest[0] < PARTITIONS:  # not all servers have data yet
            continue
        horizon = latest[1] if latest[1] == END else latest[1][:13] + ":00:00Z"
        rows = con.execute(
            f"SELECT path, count(*), count(DISTINCT user) FROM read_parquet('{files}') "
            "WHERE type = 'request' AND method = 'GET' AND path LIKE '/st/%' "
            "AND status IN (200, 304) AND time < ? GROUP BY path",
            [horizon],
        ).fetchall()
        runs += 1
        with r.pipeline(transaction=True) as pipe:  # replace the old result in one step
            pipe.delete("batch:views", "batch:viewers")
            if rows:
                pipe.hset("batch:views", mapping={p: v for p, v, _ in rows})
                pipe.hset("batch:viewers", mapping={p: u for p, _, u in rows})
            pipe.set("batch:horizon", horizon)
            pipe.set("batch:runs", runs)
            pipe.execute()
        total = sum(v for _, v, _ in rows)
        log(
            f"batch run {runs}: {total} views of {len(rows)} photos before {horizon}, "
            f"{time.monotonic() - start:.1f} s"
        )


def speed_layer():
    """Count each view in the bucket of its hour. Offsets are committed every 5 s."""
    r = store()
    conf = {"enable.auto.offset.store": True, "session.timeout.ms": 10_000}
    c = consumer("speed-layer", [TOPIC], **conf)
    while True:
        msg = c.poll(1.0)
        if msg is None or msg.error():
            continue
        e = json.loads(msg.value())
        with r.pipeline(transaction=False) as pipe:
            if e["type"] == "request" and is_view(e):
                pipe.hincrby(f"speed:views:{e['time'][:13]}", e["path"], 1)
            pipe.hset("speed:latest", e["server"], e["time"])
            pipe.execute()


def serving():
    import uvicorn
    from fastapi import FastAPI

    app = FastAPI(title="view counts")
    paths = photo_data.photos().set_index("photo_id").path
    r = store()

    @app.get("/photos/{photo_id}/views")
    def views(photo_id: int) -> dict:
        path = paths[photo_id]
        horizon = r.get("batch:horizon") or "2021-12-06T00:00:00Z"
        batch = int(r.hget("batch:views", path) or 0)
        buckets = [k for k in r.scan_iter("speed:views:*") if k[12:] >= horizon[:13]]
        speed = sum(int(v or 0) for v in (r.hget(k, path) for k in buckets))
        return {
            "photo_id": photo_id,
            "views": batch + speed,
            "batch": batch,
            "speed": speed,
            "batch_until": horizon,
        }

    @app.get("/status")
    def status() -> dict:
        return {
            "batch_until": r.get("batch:horizon"),
            "batch_runs": int(r.get("batch:runs") or 0),
            "speed_latest": r.hgetall("speed:latest"),
        }

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")


COMPONENTS = {
    f.__name__.replace("_", "-"): f
    for f in [log_shipper, archiver, batch_layer, speed_layer, serving]
}

if __name__ == "__main__":
    common.set_name(sys.argv[1])
    COMPONENTS[sys.argv[1]]()
