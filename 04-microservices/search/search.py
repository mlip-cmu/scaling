"""The search service (Python): an index from keywords to the photos of each user.

Its data: the objects in each photo and its owner (from photos.csv).
"""

import csv
from collections import defaultdict

from fastapi import FastAPI

index: dict[str, list[tuple[int, int]]] = defaultdict(list)  # keyword -> (photo, user)
with open("photos.csv", newline="") as f:
    for row in csv.DictReader(f):
        for o in row["objects"].split(";"):
            index[o].append((int(row["photo_id"]), int(row["user_id"])))

app = FastAPI(title="search")


@app.get("/search")
def search(q: str, user_id: int) -> list[int]:
    return [pid for pid, uid in index.get(q, []) if uid == user_id]
