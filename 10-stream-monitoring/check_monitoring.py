"""Wait until the system has processed all uploads, then read the monitoring data: metrics from
Prometheus (the four golden signals) and traces from Jaeger. Start the system first
(`docker compose up -d --build`)."""

import collections
import subprocess
import time
from datetime import UTC, datetime, timedelta

import httpx

prom = httpx.Client(base_url="http://localhost:9090/api/v1", timeout=10)
jaeger = httpx.Client(base_url="http://localhost:16686/api", timeout=30)


def query(q: str) -> list[dict]:
    return prom.get("/query", params={"query": q}).json()["data"]["result"]


def value(q: str) -> float:
    r = query(q)
    return float(r[0]["value"][1]) if r else 0.0


print("1. Waiting until the object detectors have processed all 523 uploads ...")
done_q = 'sum(messages_processed_total{component="object-detector"}) + ' + (
    'sum(messages_failed_total{component="object-detector"}) or vector(0)'
)
for _ in range(300):
    try:
        done = value(done_q)
    except (httpx.HTTPError, KeyError):
        done = 0
    if done >= 523 and value("sum(consumer_lag)") == 0:
        break
    time.sleep(3)
time.sleep(5)  # the last spans and metrics
print(f"   {done:.0f} photos processed or failed; no consumer group is behind.\n")

print("2. The four golden signals for the whole run (from Prometheus):")
print("   traffic (messages processed) and errors (messages failed):")
failed = {
    r["metric"]["component"]: float(r["value"][1])
    for r in query("sum by (component) (messages_failed_total)")
}
for r in query("sum by (component) (messages_processed_total)"):
    c = r["metric"]["component"]
    print(f"     {c:<22} {float(r['value'][1]):>5.0f} processed {failed.get(c, 0):>4.0f} failed")
print("   latency: processing time of the object detectors (95th percentile):")
for r in query(
    "histogram_quantile(0.95, sum by (le, service, instance) "
    '(increase(processing_seconds_bucket{component="object-detector"}[15m])))'
):
    m = r["metric"]
    print(f"     {m['service']:<22} {m['instance']:<18} {float(r['value'][1]):.2f} s")
print("   saturation: the largest lag of each partition of new_photos (object detection):")
for r in sorted(
    query(
        'max_over_time(sum by (partition, service) (consumer_lag{component="object-detector", '
        'topic="new_photos"})[15m:2s])'
    ),
    key=lambda r: int(r["metric"]["partition"]),
):
    m = r["metric"]
    print(f"     partition {m['partition']} ({m['service']}): {float(r['value'][1]):.0f} messages")
print("   waiting time in the queue (95th percentile), per component:")
for r in query(
    "histogram_quantile(0.95, sum by (le, component) (increase(queue_wait_seconds_bucket[15m])))"
):
    print(f"     {r['metric']['component']:<22} {float(r['value'][1]):.1f} s")

print("\n3. Traces (from Jaeger): the photo that took longest from upload to the database")
now = datetime.now(UTC)
params = {
    "query.service_name": "photo-uploader",
    "query.start_time_min": (now - timedelta(minutes=30)).isoformat(),
    "query.start_time_max": now.isoformat(),
    "query.search_depth": 1000,
}
result = jaeger.get("/v3/traces", params=params).json()["result"]["resourceSpans"]
slow_host = subprocess.run(
    ["docker", "compose", "ps", "-q", "object-detector-slow"], capture_output=True, text=True
).stdout.strip()[:12]


def attrs(items: list[dict]) -> dict:
    return {a["key"]: next(iter(a["value"].values())) for a in items}


traces: dict[str, list[dict]] = collections.defaultdict(list)
for rs in result:  # the OTLP format: spans grouped by the component that sent them
    resource = attrs(rs["resource"]["attributes"])
    for scope in rs["scopeSpans"]:
        for s in scope["spans"]:
            traces[s["traceId"]].append(
                {
                    "service": resource["service.name"],
                    "host": resource["service.instance.id"],
                    "name": s["name"],
                    "start": int(s["startTimeUnixNano"]) / 1e9,
                    "end": int(s["endTimeUnixNano"]) / 1e9,
                    "attrs": attrs(s.get("attributes", [])),
                }
            )


def duration(spans: list[dict]) -> float:
    return max(s["end"] for s in spans) - min(s["start"] for s in spans)


trace_id = max(traces, key=lambda t: duration(traces[t]))
longest = traces[trace_id]
t0 = min(s["start"] for s in longest)
print(f"   {'start':>7} {'duration':>9}  service: operation")
for s in sorted(longest, key=lambda s: s["start"]):
    mark = " (the slow instance)" if s["host"] == slow_host else ""
    wait = s["attrs"].get("queue.wait_s")
    wait_text = f", waited {wait:.1f} s in the queue" if wait is not None else ""
    print(
        f"   {s['start'] - t0:>6.2f}s {s['end'] - s['start']:>8.3f}s  "
        f"{s['service']}: {s['name']}{mark}{wait_text}"
    )
print(f"   ({len(traces)} traces in Jaeger; this one: http://localhost:16686/trace/{trace_id})")

pre = [
    (s["host"], s["end"] - s["start"])
    for t in traces.values()
    for s in t
    if s["name"] == "preprocess"
]
slow = [d for h, d in pre if h == slow_host]
fast = [d for h, d in pre if h != slow_host]
print(
    f"\n   the span preprocess takes {1000 * sum(fast) / max(len(fast), 1):.1f} ms on average on "
    f"the 2 normal instances ({len(fast)} spans),"
)
print(
    f"   and {1000 * sum(slow) / max(len(slow), 1):.1f} ms on object-detector-slow "
    f"({len(slow)} spans)"
)
