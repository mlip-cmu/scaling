# 05 · Batch processing with MapReduce and Hadoop

The four web servers of the photo service write access logs: about 50,000 requests in three
days ([dataset](../photo-data/), `logs/web/access-web-*.log`). The team wants to know which
photos are viewed most, and wants features per photo (views, viewers) as training data for a
model.

**Problem.** Log files are large, unstructured, and spread over many machines. At scale, one
machine cannot read all of them in useful time, and moving all logs over the network to one
place is expensive.

**Idea.** Split the job into two steps without side effects: a *map* step that processes one
line at a time and writes key-value pairs, and a *reduce* step that combines all values of
one key. The framework runs the map step in parallel on the machines where the data is
stored (data locality), moves only the much smaller map output (the *shuffle*, sorted and
grouped by key), and runs a task again when it fails. The same two scripts work on one
machine with a shell pipeline, and on a Hadoop cluster.

The mapper reads log lines and writes one pair per photo view (`mapper.py`):

```python
for line in sys.stdin:
    f = line.split()
    # 192.0.2.7 - ckaestne [06/Dec/2021:02:49:12 +0000] "GET /st/u211/1U6uFl47Fy.jpg HTTP/1.1" 200
    if len(f) > 8 and f[5] == '"GET' and f[6].startswith("/st/") and f[8] in ("200", "304"):
        print(f"{f[6]}\t1")
```

On one machine, `sort` does the shuffle (`local.sh`); on the cluster, Hadoop Streaming runs
the same scripts (`run_hadoop.py`):

```sh
cat access-*.log | python3 mapper.py | sort | python3 reducer.py
mapred streaming -files mapper.py,reducer.py -mapper 'python3 mapper.py' \
    -combiner 'python3 reducer.py' -reducer 'python3 reducer.py' -input /logs -output /out/views
```

## What the code shows

- `local.sh`:
  1. The classic shell pipeline (`awk '{print $7}' | sort | uniq -c | sort -r -n | head -n 5`)
     finds the most requested paths. These are static files and the login page
     (`/favicon.ico` with 1,251 requests), not photos.
  2. With the mapper (only photo views) and the reducer: the most viewed photo has 421 views.
- `compose.yaml`: a Hadoop cluster in Docker: a NameNode (HDFS), a ResourceManager (YARN), and
  3 workers. Each worker stores data (DataNode) and runs tasks (NodeManager).
- `run_hadoop.py`:
  1. HDFS stores the 4 log files in blocks of 1 MB (small for the demo; the default is
     128 MB): 12 blocks, and each block on 2 of the 3 workers (replication).
  2. The job runs one map task per block. Almost all map tasks are data-local: they run on a
     worker that stores their block. The first attempt of one map task crashes; Hadoop runs
     it again, and the job succeeds. The result is the same as on one machine.
  3. The shuffle: the 12 map tasks write 28,888 pairs (0.76 MB); the input was 9.9 MB. A
     combiner (the reducer, run on the output of each map task) reduces the data that goes
     over the network to 20,416 records (0.58 MB). It helps only a little here, because most
     photos are viewed only once or twice per block.
  4. A second job extracts features for a model: views, number of viewers, and the share of
     views from the mobile app, for each of the 12,305 viewed photos (`out/features.tsv`).

## Tools

- [Apache Hadoop](https://hadoop.apache.org): a framework for distributed storage (HDFS) and
  batch processing (MapReduce on YARN). Here: a cluster of 5 containers with the official
  image `apache/hadoop`.
- [Hadoop Streaming](https://hadoop.apache.org/docs/current/hadoop-streaming/HadoopStreaming.html):
  runs any program as mapper and reducer (input on stdin, output on stdout). Here: the Python
  scripts.
- Unix shell tools (`awk`, `sort`, `uniq`, `head`): the same kind of processing on one
  machine: immutable inputs, new outputs, and small programs in a pipeline.
- [Docker Compose](https://docs.docker.com/compose/): starts the cluster from one file.

Modern dataflow engines like [Apache Spark](https://spark.apache.org) and
[Apache Flink](https://flink.apache.org) follow the same ideas with more flexible programs.

## Run

With [Docker](https://docs.docker.com/get-docker/) and [uv](https://docs.astral.sh/uv/):

```sh
./local.sh                  # the shell pipeline and map | sort | reduce on one machine
docker compose up -d        # start the cluster (HDFS: http://localhost:9870, YARN: :8088)
uv run run_hadoop.py        # store the logs in HDFS and run the jobs (about 3 minutes)
docker compose down -v      # stop and remove the cluster
```
