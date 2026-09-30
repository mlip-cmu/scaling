"""More consumers in one group process a topic faster, but only up to the number of partitions.

Each run starts N workers in a new consumer group. The group reads all messages of
`new_photos` from the beginning (Kafka keeps them after the other groups read them) and each
worker "processes" a photo in about 0.1 s. Start the system first (`docker compose up -d`).
"""

import multiprocessing as mp
import random
import sys
import time

from confluent_kafka import Consumer, TopicPartition

from common import BOOTSTRAP, consumer

TOPIC = "new_photos"


def worker(group: str, name: str, results) -> None:
    assigned: list[int] = []

    def on_assign(c, partitions):
        assigned[:] = sorted(p.partition for p in partitions)
        results.put(("assign", name, list(assigned)))

    c = consumer(group, [TOPIC], verbose=False, on_assign=on_assign)
    while True:
        msg = c.poll(0.5)
        if msg is None or msg.error():
            continue
        time.sleep(random.Random(msg.offset()).uniform(0.05, 0.15))  # "model inference"
        c.store_offsets(msg)
        results.put(("done", name, msg.partition()))


def run(n: int, total: int) -> tuple[float, dict]:
    results = mp.Queue()
    group = f"scaling-demo-{n}-{int(time.time())}"
    procs = [mp.Process(target=worker, args=(group, f"w{i + 1}", results)) for i in range(n)]
    start = time.monotonic()
    for p in procs:
        p.start()
    done, per_worker, parts = 0, {f"w{i + 1}": 0 for i in range(n)}, {}
    while done < total:
        kind, name, value = results.get(timeout=120)
        if kind == "assign":
            parts[name] = value
        else:
            done += 1
            per_worker[name] += 1
    elapsed = time.monotonic() - start
    for p in procs:
        p.terminate()
    return elapsed, {w: (parts.get(w, []), per_worker[w]) for w in per_worker}


if __name__ == "__main__":
    c = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": "scaling-demo"})
    meta = c.list_topics(TOPIC, timeout=10).topics[TOPIC].partitions
    sizes = [c.get_watermark_offsets(TopicPartition(TOPIC, p))[1] for p in sorted(meta)]
    total = sum(sizes)
    print(f"{TOPIC}: {total} messages in {len(sizes)} partitions {sizes}\n")
    print(f"{'workers':>7} {'time':>7} {'photos/s':>8}   partitions (messages) per worker")
    counts = [int(a) for a in sys.argv[1:]] or [1, 2, 3, 6, 8]
    for n in counts:
        elapsed, workers = run(n, total)
        detail = "  ".join(f"{p or '-'} ({k})" for p, k in workers.values())
        print(f"{n:>7} {elapsed:>6.1f}s {total / elapsed:>8.1f}   {detail}", flush=True)
