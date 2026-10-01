"""The keyword service (Python): the object detection model. It is stateless, so compose.yaml
starts several instances behind a load balancer (nginx).

Its data: the objects in each photo (from photos.csv), which the "model" finds with 90%
probability.
"""

import csv
import random
import socket
import time

from fastapi import FastAPI, HTTPException

HOST = socket.gethostname()[:12]  # the container ID: which instance answers

with open("photos.csv", newline="") as f:
    truth = {int(row["photo_id"]): row["objects"].split(";") for row in csv.DictReader(f)}

app = FastAPI(title="keywords")


@app.get("/keywords/{photo_id}")
def keywords(photo_id: int) -> dict:
    if photo_id not in truth:
        raise HTTPException(404, "no such photo")
    rng = random.Random(photo_id)
    time.sleep(rng.uniform(0.05, 0.15))  # model inference
    objects = [o for o in truth[photo_id] if rng.random() < 0.9]
    return {"photo_id": photo_id, "keywords": objects, "instance": HOST}
