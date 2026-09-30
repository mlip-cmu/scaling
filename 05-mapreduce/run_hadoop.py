"""Run the MapReduce jobs on the Hadoop cluster (start it first: `docker compose up -d`)."""

import re
import subprocess
import time
from pathlib import Path


def hadoop(command: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command in the NameNode container (the Hadoop client is installed there)."""
    return subprocess.run(
        ["docker", "compose", "exec", "-T", "namenode", "bash", "-c", command],
        capture_output=True,
        text=True,
        check=check,
    )


def counters(log: str) -> dict[str, int]:
    return {k.strip(): int(v) for k, v in re.findall(r"^\s+([A-Za-z][\w ()-]+)=(\d+)$", log, re.M)}


def streaming(name: str, mapper: str, reducer: str, combiner: str | None = None, env=""):
    hadoop(f"hdfs dfs -rm -r -f /out/{name}")
    files = ",".join(f"/job/{f}" for f in {mapper, reducer, combiner} if f)
    command = (
        f"mapred streaming -D mapreduce.job.name={name} -D mapreduce.job.reduces=2 "
        f"-files {files} -mapper 'python3 {mapper}' -reducer 'python3 {reducer}' "
        + (f"-combiner 'python3 {combiner}' " if combiner else "")
        + (f"-cmdenv {env} " if env else "")
        + f"-input /logs -output /out/{name}"
    )
    start = time.monotonic()
    result = hadoop(command)
    return counters(result.stdout + result.stderr), time.monotonic() - start


print("1. Wait for HDFS with 3 data nodes, then store the 4 log files in HDFS.")
for _ in range(60):
    report = hadoop("hdfs dfsadmin -report", check=False).stdout
    if "Live datanodes (3)" in report:
        break
    time.sleep(2)
hosts = dict(re.findall(r"Name: ([\d.]+):\d+ \((?:[^)]*)\)\nHostname: (\w+)", report))
hadoop("hdfs dfs -mkdir -p /logs && hdfs dfs -put -f /data/logs/web/access-*.log /logs/")
fsck = hadoop("hdfs fsck /logs -files -blocks -locations").stdout
for f in re.findall(r"^/logs/(\S+) (\d+) bytes.*?(\d+) block", fsck, re.M):
    print(f"   {f[0]}: {int(f[1]) / 1e6:.1f} MB in {f[2]} blocks of 1 MB")
blocks = re.findall(r"blk_\d+_\d+ len=(\d+) Live_repl=(\d+)\s+\[(.*)\]", fsck)
places = [
    sorted(hosts.get(ip, ip) for ip in re.findall(r"\[([\d.]+):\d+", "[" + b[2])) for b in blocks
]
print(f"   {len(blocks)} blocks, each stored on 2 of the 3 workers, for example:")
for p in places[:3]:
    print(f"   {' and '.join(p)}")

print("\n2. Count the views of each photo (combiner on; the first attempt of map task 3 crashes).")
c, secs = streaming("views", "mapper.py", "reducer.py", "reducer.py", env="FAIL_TASK=000003")
maps, failed = c["Launched map tasks"], c.get("Failed map tasks", 0)
print(
    f"   {maps - failed} map tasks (one per block) + {failed} again after the crash, "
    f"{c['Launched reduce tasks']} reduce tasks, {secs:.0f} s"
)
print(
    f"   data-local map tasks: {c.get('Data-local map tasks', 0)} of {maps} (the task ran on a "
    "worker that stores its block)"
)
print("   the job succeeded: map tasks have no side effects, so Hadoop can run one again")
top = hadoop("hdfs dfs -cat /out/views/part-* | sort -t$'\\t' -k2,2nr -k1,1 | head -n 5").stdout
Path("out/top_photos_hadoop.tsv").write_text(top)
print("   the 5 most viewed photos:")
print("".join(f"   {line}\n" for line in top.splitlines()), end="")
local = Path("out/top_photos_local.tsv")
if local.exists():
    print(f"   the same as on one machine (local.sh): {local.read_text() == top}")

print("\n3. The shuffle moves the map output over the network to the reducers:")
c2, _ = streaming("views-no-combiner", "mapper.py", "reducer.py")
print(f"   map output: {c['Map output records']} records ({c['Map output bytes'] / 1e6:.2f} MB)")
print(
    f"   without a combiner, the reducers receive {c2['Reduce input records']} records "
    f"({c2['Reduce shuffle bytes'] / 1e6:.2f} MB)"
)
print(
    f"   with the combiner (a reduce on each map task first): {c['Reduce input records']} "
    f"records ({c['Reduce shuffle bytes'] / 1e6:.2f} MB)"
)

print("\n4. Feature extraction for a model: views, viewers, and the share of app views per photo.")
c3, _ = streaming("features", "features_mapper.py", "features_reducer.py")
features = hadoop("hdfs dfs -cat /out/features/part-* | sort -t$'\\t' -k2,2nr -k1,1").stdout
Path("out/features.tsv").write_text("path\tviews\tviewers\tapp_share\n" + features)
print(f"   {c3['Reduce output records']} photos in out/features.tsv; the most viewed:")
print("   path                     views viewers app_share")
print("".join(f"   {line}\n" for line in features.splitlines()[:3]).replace("\t", "  "), end="")
