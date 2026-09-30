"""The components of the photo service that communicate through Kafka topics.

Each component declares which topics it consumes and produces. Run one with
`python components.py <name>` (the containers in compose.yaml do this).
"""

import collections
import json
import os
import random
import sqlite3
import sys
import time

import pandas as pd

import common
import photo_data
from common import consumer, ensure_topics, log, producer, send

TOPICS = {"new_photos": 6, "detected_objects": 3, "friends_detected": 3}
COMPONENTS: dict[str, dict] = {}


def component(name, consumes=(), produces=(), group=None):
    def register(run):
        COMPONENTS[name] = {
            "run": run,
            "consumes": list(consumes),
            "produces": list(produces),
            "group": group or name,
        }
        return run

    return register


def process(name: str, handle) -> None:
    """Consume messages one at a time: handle each, then mark it as processed (at-least-once)."""
    spec = COMPONENTS[name]
    ensure_topics(TOPICS)
    c = consumer(spec["group"], spec["consumes"])
    p = producer() if spec["produces"] else None
    log(f"consumes {spec['consumes']} in group '{spec['group']}'")
    while True:
        msg = c.poll(1.0)
        if msg is None:
            continue
        if msg.error():
            log(f"error: {msg.error()}")
            continue
        handle(json.loads(msg.value()), msg, p)
        if p:
            p.flush()  # the results are stored in Kafka before the input counts as processed
        c.store_offsets(msg)


_seen = collections.Counter()


def progress(msg) -> None:
    _seen[msg.partition()] += 1
    if sum(_seen.values()) % 25 == 0:
        log(f"processed {sum(_seen.values())} photos, per partition: {dict(sorted(_seen.items()))}")


# --- producers ---------------------------------------------------------------------------


@component("photo-uploader", produces=["new_photos"])
def photo_uploader():
    """Replays the uploads of 2021-12-06 to 2021-12-08: 3 days in about a minute."""
    ensure_topics(TOPICS)
    source = os.environ.get("UPLOAD_SOURCE", "app")  # app or web: two separate uploaders
    speedup = float(os.environ.get("SPEEDUP", 4000))
    photos = photo_data.photos()
    cams = photo_data.cameras().set_index("camera_id")
    days = photos[(photos.upload_date >= "2021-12-06") & (photos.upload_date < "2021-12-09")]
    is_web = days.camera_id.map(cams.manufacturer).isin(["Canon", "Sony", "Nikon", "Fujifilm"])
    mine = days[is_web == (source == "web")]
    p = producer()
    time.sleep(float(os.environ.get("START_DELAY", 5)))
    start, t0 = days.upload_date.min(), time.monotonic()
    log(f"uploading {len(mine)} photos ({source})")
    for r in mine.itertuples():
        wait = (r.upload_date - start).total_seconds() / speedup - (time.monotonic() - t0)
        time.sleep(max(wait, 0))
        send(
            p,
            "new_photos",
            r.user_id,
            {
                "photo_id": r.photo_id,
                "user_id": r.user_id,
                "path": r.path,
                "format": r.format,
                "size": r.size,
                "uploaded": r.upload_date.isoformat(),
                "source": source,
            },
        )
    p.flush()
    log(f"done: {len(mine)} photos sent")
    while True:
        time.sleep(3600)


# --- model inference (dummy models: the truth, with some mistakes, and a delay) -----------

OBJECTS = sorted({o for objs in photo_data.photos().objects for o in objs.split(";")})


def _truth(column: str) -> dict[int, list[str]]:
    photos = photo_data.photos()
    return {
        p: v.split(";") if v else [] for p, v in zip(photos.photo_id, photos[column], strict=True)
    }


@component("object-detector", ["new_photos"], ["detected_objects"], group="object-detection")
def object_detector():
    truth = _truth("objects")

    def handle(photo, msg, p):
        rng = random.Random(photo["photo_id"])  # the same answer if a photo is processed twice
        time.sleep(rng.uniform(0.15, 0.45))
        found = [o for o in truth[photo["photo_id"]] if rng.random() < 0.9]
        if rng.random() < 0.1:
            found.append(rng.choice(OBJECTS))
        progress(msg)
        send(
            p,
            "detected_objects",
            photo["photo_id"],
            {
                "photo_id": photo["photo_id"],
                "user_id": photo["user_id"],
                "uploaded": photo["uploaded"],
                "objects": found,
                "worker": common.NAME,
                "partition": msg.partition(),
            },
        )

    process("object-detector", handle)


@component("friend-detector", ["new_photos"], ["friends_detected"], group="friend-detection")
def friend_detector():
    truth = _truth("people")
    users = photo_data.users().user_id.tolist()

    def handle(photo, msg, p):
        rng = random.Random(-photo["photo_id"])
        time.sleep(rng.uniform(0.1, 0.3))
        found = [int(u) for u in truth[photo["photo_id"]] if rng.random() < 0.85]
        if rng.random() < 0.03:
            found.append(rng.choice(users))
        progress(msg)
        if found:
            send(
                p,
                "friends_detected",
                photo["photo_id"],
                {
                    "photo_id": photo["photo_id"],
                    "user_id": photo["user_id"],
                    "friends": found,
                    "worker": common.NAME,
                },
            )

    process("friend-detector", handle)


# --- consumers of the results ------------------------------------------------------------


@component("notification-service", ["friends_detected"])
def notification_service():
    names = photo_data.users().set_index("user_id").account_name
    sent = 0

    def handle(event, msg, p):
        nonlocal sent
        for f in event["friends"]:
            sent += 1
            log(
                f"#{sent} to {names[f]}: {names[event['user_id']]} uploaded a photo of you "
                f"(photo {event['photo_id']})"
            )

    process("notification-service", handle)


@component("object-statistics", ["detected_objects"])
def object_statistics():
    """Three kinds of stream queries: per event, over all events so far, and per time window."""
    total = collections.Counter()
    windows: dict[pd.Timestamp, collections.Counter] = collections.defaultdict(collections.Counter)
    late = collections.Counter()
    latest = pd.Timestamp.min.tz_localize("UTC")
    n = 0

    def handle(event, msg, p):
        nonlocal latest, n
        n += 1
        t = pd.Timestamp(event["uploaded"])
        window = t.floor("6h")  # tumbling windows of 6 hours (upload time, not arrival time)
        total.update(event["objects"])  # incremental: all events so far
        if window in windows and windows[window] is None:
            late[window] += 1  # the window was already reported: the event came too late
        else:
            windows[window].update(event["objects"])
        latest = max(latest, t)
        for w, counts in sorted(windows.items()):
            if counts is not None and w + pd.Timedelta("8h") < latest:  # 2 hours for stragglers
                top = ", ".join(f"{o} {c}" for o, c in counts.most_common(3))
                log(
                    f"window {w:%m-%d %H:%M} to {w + pd.Timedelta('6h'):%H:%M}: "
                    f"{sum(counts.values())} objects, top: {top}"
                )
                windows[w] = None
        if n % 100 == 0:
            log(
                f"after {n} photos, all time: {dict(total.most_common(4))}; "
                f"late events: {sum(late.values())}"
            )

    process("object-statistics", handle)


@component("db-writer", ["detected_objects", "friends_detected"])
def db_writer():
    db = sqlite3.connect(os.environ.get("DB_PATH", "out/photos.db"))
    db.execute(
        "CREATE TABLE IF NOT EXISTS keywords (photo_id INTEGER PRIMARY KEY, "
        "objects TEXT, friends TEXT, writes INTEGER DEFAULT 1)"
    )

    def handle(event, msg, p):
        column, value = (
            ("objects", ";".join(event["objects"]))
            if msg.topic() == "detected_objects"
            else ("friends", ";".join(map(str, event["friends"])))
        )
        # an upsert: writing the same result twice does not change the table (idempotent)
        db.execute(
            f"INSERT INTO keywords (photo_id, {column}) VALUES (?, ?) "
            f"ON CONFLICT (photo_id) DO UPDATE SET {column} = excluded.{column}, "
            "writes = writes + 1",
            (event["photo_id"], value),
        )
        db.commit()

    process("db-writer", handle)


if __name__ == "__main__":
    common.set_name(sys.argv[1])
    COMPONENTS[sys.argv[1]]["run"]()
