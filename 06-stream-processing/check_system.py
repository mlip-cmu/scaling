"""Wait until the running system has processed all uploads, then show its state.

Start the system first: `docker compose up -d`.
"""

import sqlite3
import subprocess
import time

from confluent_kafka import Consumer, ConsumerGroupTopicPartitions, KafkaException, TopicPartition

import photo_data
from common import BOOTSTRAP, admin, lag
from components import COMPONENTS, TOPICS

photos = photo_data.photos()
uploads = photos[(photos.upload_date >= "2021-12-06") & (photos.upload_date < "2021-12-09")]
db = sqlite3.connect("out/photos.db")

print(f"1. Waiting until the database has keywords for all {len(uploads)} uploads ...")
for _ in range(300):
    try:
        done = db.execute("SELECT count(*) FROM keywords WHERE objects IS NOT NULL").fetchone()[0]
    except sqlite3.OperationalError:
        done = 0
    groups = {spec["group"]: spec["consumes"] for spec in COMPONENTS.values() if spec["consumes"]}
    try:
        behind = sum(sum(lag(g, t).values()) for g, topics in groups.items() for t in topics)
    except KafkaException:  # the broker is still starting
        behind = -1
    if done == len(uploads) and behind == 0:
        break
    time.sleep(2)
print(f"   {done} photos have keywords; no consumer group is behind.\n")

print("2. Messages per partition (the key is the user, so all photos of a user are in one")
print("   partition; the partition of the most active user gets more messages):")
c = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": "check"})
for topic, n in TOPICS.items():
    counts = [c.get_watermark_offsets(TopicPartition(topic, p), timeout=5)[1] for p in range(n)]
    print(f"   {topic:<17} {sum(counts):>4} messages: {counts}")
top = uploads.user_id.value_counts()
print(f"   most active user on these days: {top.index[0]} with {top.iloc[0]} photos\n")

print("3. Consumer groups: each group gets every message; the members of a group share the")
print("   partitions.")
a = admin()
names = sorted({spec["group"] for spec in COMPONENTS.values() if spec["consumes"]})
for g, f in a.describe_consumer_groups(names).items():
    d = f.result()
    parts = []
    for m in d.members:
        by_topic: dict[str, list[int]] = {}
        for tp in m.assignment.topic_partitions:
            by_topic.setdefault(tp.topic, []).append(tp.partition)
        parts.append(" ".join(f"{t}{sorted(p)}" for t, p in sorted(by_topic.items())))
    print(f"   {g:<20} {len(d.members)} member(s): " + " | ".join(sorted(parts)))
req = [ConsumerGroupTopicPartitions("object-detection", [TopicPartition("new_photos", 0)])]
offset = a.list_consumer_group_offsets(req)["object-detection"].result().topic_partitions[0]
print(f"   (object-detection has read partition 0 up to offset {offset.offset})\n")

rows, writes, friends = db.execute(
    "SELECT count(*), sum(writes), sum(friends IS NOT NULL) FROM keywords"
).fetchone()
print(f"4. Database: {rows} photos, {friends} with friends, {writes} writes (one per result).")
logs = subprocess.run(
    ["docker", "compose", "logs", "--no-log-prefix", "notification-service"],
    capture_output=True,
    text=True,
).stdout
sent = logs.count("uploaded a photo of you")
print(f"   The notification service sent {sent} notifications.")
truth = uploads.set_index("photo_id").objects.str.split(";")
found = dict(db.execute("SELECT photo_id, objects FROM keywords").fetchall())
hits = sum(len(set(truth[p]) & set(o.split(";"))) for p, o in found.items() if o)
print(
    f"   The (dummy) object detector found {hits / truth.map(len).sum():.0%} of the true objects."
)
