"""Kafka keeps the order of messages only within one partition.

For each of 20 photos, 4 events happen in this order: add, set a title, apply a filter,
delete. Three consumers in one group apply the events to a table of photos. With the photo
as the message key, all events of a photo go to the same partition and one consumer applies
them in order. Without a key, the events of one photo are spread over the partitions.
Start Kafka first (`docker compose up -d kafka`).
"""

import json
import random
import threading
import time
import uuid

from common import consumer, ensure_topics, producer

EVENTS = ["addPhoto", "updatePhotoData", "replacePhoto", "deletePhoto"]
PHOTOS = range(133422131, 133422151)


def run(keyed: bool) -> dict[int, list[str]]:
    topic = f"photo_edits_{uuid.uuid4().hex[:8]}"
    ensure_topics({topic: 3})
    p = producer()
    for photo in PHOTOS:
        for i, e in enumerate(EVENTS):
            value = json.dumps({"photo_id": photo, "seq": i, "event": e})
            p.produce(topic, key=str(photo) if keyed else None, value=value)
    p.flush()
    applied: dict[int, list[str]] = {photo: [] for photo in PHOTOS}
    lock, stop = threading.Lock(), threading.Event()

    def worker(i: int) -> None:
        c = consumer(f"editor-{topic}", [topic], verbose=False)
        rng = random.Random(i)
        while not stop.is_set():
            msg = c.poll(0.5)
            if msg is None or msg.error():
                continue
            time.sleep(rng.uniform(0, 0.02))
            e = json.loads(msg.value())
            with lock:
                applied[e["photo_id"]].append(e["event"])
            c.store_offsets(msg)
        c.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    while sum(map(len, applied.values())) < len(PHOTOS) * len(EVENTS):
        time.sleep(0.2)
    stop.set()
    for t in threads:
        t.join()
    return applied


if __name__ == "__main__":
    for keyed in (True, False):
        applied = run(keyed)
        wrong = {p: a for p, a in applied.items() if a != EVENTS}
        alive = [p for p, a in applied.items() if a[-1] != "deletePhoto"]
        print(
            f"{'with the photo as key' if keyed else 'without a key'}: events of "
            f"{len(wrong)} of {len(applied)} photos applied out of order; "
            f"{len(alive)} deleted photos are still visible"
        )
        for p, a in list(wrong.items())[:2]:
            print(f"   photo {p}: {' -> '.join(a)}")
