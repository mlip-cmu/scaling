"""Use the photo service through its API gateway. Start it first: `docker compose up -d --build`."""

import collections
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

import photo_data

api = httpx.Client(base_url="http://localhost:8080/api", timeout=10)
auth = {"Authorization": "Bearer token-ckaestne"}

for _ in range(60):  # wait until all services are up
    try:
        if api.get("/photos/133422131", headers=auth).status_code == 200:
            break
    except httpx.TransportError:
        pass
    time.sleep(1)

print("1. The gateway is the only entry point, and it checks who calls")
print(f"   without a token:   {api.get('/photos/133422131').status_code}")
r = api.get("/photos/133422131", headers=auth)
print(f"   with a token:      {r.status_code} {r.json()}")
print(f"   an unknown photo:  {api.get('/photos/1', headers=auth).status_code}")

print("\n2. A search: the gateway calls the search service, then the photo service")
for bundle in (False, True):
    r = api.get("/search", params={"q": "christmas tree", "bundle": bundle}, headers=auth).json()
    how = "one call for all photos" if bundle else "one call per photo"
    print(f"   {how:<24} {len(r['photos'])} photos, {r['calls']:>3} remote calls, {r['ms']:.0f} ms")
local = {i: i for i in range(100_000)}
start = time.perf_counter()
for i in range(100_000):
    local[i]
per_call = (time.perf_counter() - start) / 100_000 * 1000
print(f"   for comparison, a lookup in the memory of one process: {per_call * 1000:.2f} µs")

print("\n3. The keyword service (the model) has 3 instances behind a load balancer (nginx)")


names = photo_data.users().account_name[:10].tolist()  # 10 users, below their rate limits


def keywords(n: int) -> collections.Counter:
    def call(i: int) -> httpx.Response:
        token = {"Authorization": f"Bearer token-{names[i % len(names)]}"}
        return api.get(f"/photos/{133422131 + i}/keywords", headers=token)

    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(call, range(n)))
    return collections.Counter(
        r.json()["instance"] if r.status_code == 200 else f"error {r.status_code}" for r in results
    )


print(f"   30 requests, answered by: {dict(keywords(30))}")
instances = subprocess.run(
    ["docker", "compose", "ps", "-q", "keywords"], capture_output=True, text=True
).stdout.split()
subprocess.run(["docker", "stop", "-t", "1", instances[0]], capture_output=True)
print(f"\n4. One instance ({instances[0][:12]}) stops")
time.sleep(1)
print(f"   30 requests, answered by: {dict(keywords(30))}")
print("   no errors: nginx sends the requests that fail to another instance")
subprocess.run(["docker", "start", instances[0]], capture_output=True)

print("\n5. The gateway limits the requests of each user (at most 20 per second)")
time.sleep(1)
codes = collections.Counter(
    api.get("/photos/133422131", headers=auth).status_code for _ in range(30)
)
print(f"   30 requests in a row: {dict(codes)}")
