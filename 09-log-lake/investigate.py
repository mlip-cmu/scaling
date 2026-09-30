"""Questions that nobody planned when the logs were written, answered from the raw logs in Loki.

LogQL parses the lines at query time (schema on read): `pattern`, `regexp`, `json`, and
`logfmt` extract fields from the text. Run `ship_logs.py` first.
"""

import httpx
from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig

import photo_data

loki = httpx.Client(base_url="http://localhost:3100/loki/api/v1", timeout=60)
START, END = "2021-12-06T00:00:00Z", "2021-12-09T00:00:00Z"
ACCESS = (
    '{service="nginx", file="access"} '
    '| pattern `<ip> - <user> [<_>] "<method> <path> <_>" <status> <size> <_>`'
)


def metric(q: str, time: str = END) -> list[tuple[dict, float]]:
    """An instant query at the given time (for example, [3d] means the three days before END)."""
    r = loki.get("/query", params={"query": q, "time": time}).json()["data"]["result"]
    return sorted(((x["metric"], float(x["value"][1])) for x in r), key=lambda x: -x[1])


def per_hour(q: str) -> list[tuple[dict, list]]:
    params = {"query": q, "start": START, "end": END, "step": "1h"}
    r = loki.get("/query_range", params=params).json()["data"]["result"]
    return [(x["metric"], [(int(t), float(v)) for t, v in x["values"]]) for x in r]


def lines(q: str, limit: int = 10) -> list[str]:
    params = {"query": q, "start": START, "end": END, "limit": limit, "direction": "forward"}
    r = loki.get("/query_range", params=params).json()["data"]["result"]
    return [line for _, line in sorted(v for s in r for v in s["values"])]


def hour(t: int) -> str:
    import datetime as dt

    return dt.datetime.fromtimestamp(t, dt.UTC).strftime("%m-%d %H:00")


print("1. What is in the lake: raw lines, with only a time and the labels of the source")
for m, n in metric('sum by (service, file) (count_over_time({service=~".+"}[3d]))'):
    print(f"   {m['service']:<12} {m.get('file', ''):<7} {n:>6.0f} lines")

print("\n2. Patterns in the lines, found without a parser (the Drain algorithm):")
for service in ["thumbnailer", "crashes", "auth"]:
    miner = TemplateMiner(config=TemplateMinerConfig())
    for line in lines(f'{{service="{service}"}}', limit=5000):
        miner.add_log_message(line)
    clusters = sorted(miner.drain.clusters, key=lambda c: -c.size)
    print(f"   {service}: {len(clusters)} patterns, the most frequent:")
    for c in clusters[:3]:
        print(f"     {c.size:>5}  {c.get_template()[:95]}")

print("\n3. Question: did anything go wrong with the uploads? Server errors (5xx) per hour:")
series = per_hour(f"sum(count_over_time({ACCESS} | status >= 500 [1h]))")
for t, v in series[0][1] if series else []:
    if v > 1:
        print(f"   {hour(t - 3600)} to {hour(t)[-5:]}  {v:>4.0f} requests with 5xx")
for m, n in metric(
    f"topk(3, sum by (method, path, status) (count_over_time({ACCESS} | status >= 500 [3d])))"
):
    print(f"   {m['method']} {m['path']} {m['status']}: {n:.0f} requests")
users = metric(f'count(sum by (user) (count_over_time({ACCESS} | status = "502" [3d])))')
print(f"   users with failed uploads: {users[0][1]:.0f}")

print("\n   Which components log errors on 2021-12-07? (lines with error, fatal, or critical)")
for m, n in metric(
    'sum by (service) (count_over_time({service=~".+"} |~ `(?i)error|fatal|critical` [1d]))',
    time="2021-12-08T00:00:00Z",
):
    print(f"   {m['service']:<12} {n:>5.0f} lines")
q = 'sum by (format) (count_over_time({service="thumbnailer"} |= "ERROR" '
q += "| regexp `format=(?P<format>\\w+)` [3d]))"
print(
    "   thumbnailer errors by image format: "
    + ", ".join(f"{m['format']} {n:.0f}" for m, n in metric(q))
)
q = 'sum by (platform, app_version, location) (count_over_time({service="crashes"} | json [3d]))'
print("   crash reports of the apps (top 3):")
for m, n in metric(f"topk(3, {q})"):
    print(f"     {n:>3.0f}  {m['platform']} {m['app_version']}: {m['location'][:70]}")

print("\n   What changed at that time? Deployments and starts of the thumbnailer:")
for line in lines('{service="deploy"} |= "service=thumbnailer"'):
    print(f"   {line[:110]}")
for line in lines('{service="thumbnailer"} |= "starting"'):
    print(f"   {line[:110]}")

print("\n4. Question: does someone try to break into accounts? Failed logins by address:")
q = '{service="auth"} |= "login failed" | regexp `ip=(?P<ip>\\S+)`'
for m, n in metric(f"topk(3, sum by (ip) (count_over_time({q} [3d])))"):
    print(f"   {m['ip']:<16} {n:>4.0f} failed logins")
attack = lines(f'{q} | ip="203.0.113.77"', limit=1000)
print(f"   203.0.113.77: from {attack[0][:15]} to {attack[-1][:15]}")

print("\n5. The truth (from the dataset):")
for i in photo_data.incidents()["incidents"]:
    facts = ", ".join(f"{k} {v}" for k, v in i.items() if isinstance(v, int))
    print(f"   {i['id']}: {i['start'][:16]} to {i['end'][11:16]}; {facts}")
