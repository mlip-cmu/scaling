"""Four services of the photo service. Each has one job and its own data.

- photos:   the metadata of the photos (its own copy of the data)
- keywords: the object detection model (stateless; several instances behind nginx)
- search:   an index from keywords to photos
- gateway:  the only entry point: authentication, routing, rate limits, retries

Run one with `python services.py <name>` (the containers in compose.yaml do this).
"""

import random
import socket
import sys
import time
from collections import defaultdict

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request

import photo_data

HOST = socket.gethostname()[:12]


def photos_service() -> FastAPI:
    app = FastAPI(title="photos")
    photos = photo_data.photos().set_index("photo_id")

    def info(pid: int) -> dict:
        p = photos.loc[pid]
        return {
            "photo_id": pid,
            "user_id": int(p.user_id),
            "path": p.path,
            "uploaded": p.upload_date.isoformat(),
            "title": p.title,
        }

    @app.get("/photos/{photo_id}")
    def one(photo_id: int) -> dict:
        if photo_id not in photos.index:
            raise HTTPException(404, "no such photo")
        return info(photo_id)

    @app.get("/photos")
    def many(ids: str) -> list[dict]:  # several photos in one call
        return [info(int(i)) for i in ids.split(",") if int(i) in photos.index]

    return app


def keywords_service() -> FastAPI:
    app = FastAPI(title="keywords")
    truth = photo_data.photos().set_index("photo_id").objects

    @app.get("/keywords/{photo_id}")
    def keywords(photo_id: int) -> dict:
        rng = random.Random(photo_id)
        time.sleep(rng.uniform(0.05, 0.15))  # model inference
        objects = [o for o in truth[photo_id].split(";") if rng.random() < 0.9]
        return {"photo_id": photo_id, "keywords": objects, "instance": HOST}

    return app


def search_service() -> FastAPI:
    app = FastAPI(title="search")
    index: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for pid, uid, objs in photo_data.photos()[["photo_id", "user_id", "objects"]].itertuples(
        index=False
    ):
        for o in objs.split(";"):
            index[o].append((pid, uid))

    @app.get("/search")
    def search(q: str, user_id: int) -> list[int]:
        return [pid for pid, uid in index.get(q, []) if uid == user_id]

    return app


def gateway() -> FastAPI:
    app = FastAPI(title="gateway")
    client = httpx.Client(timeout=2)
    backends = {
        "photos": "http://photos:8000",
        "keywords": "http://keywords-lb:8000",
        "search": "http://search:8000",
    }
    users = photo_data.users().set_index("account_name").user_id
    tokens = {f"token-{name}": int(uid) for name, uid in users.items()}  # a demo "identity"
    calls: dict[int, list[float]] = defaultdict(list)

    def user(request: Request) -> int:
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        if token not in tokens:
            raise HTTPException(401, "unknown token")
        uid = tokens[token]
        now = time.monotonic()
        calls[uid] = [t for t in calls[uid] if now - t < 1] + [now]
        if len(calls[uid]) > 20:  # at most 20 requests per second per user
            raise HTTPException(429, "too many requests")
        return uid

    def get(service: str, path: str, retries: int = 1):
        for attempt in range(retries + 1):
            try:
                r = client.get(backends[service] + path)
                if r.status_code < 400:
                    return r.json()
                if r.status_code < 500:  # an error of the request: do not try again
                    raise HTTPException(r.status_code, r.json().get("detail"))
            except httpx.TransportError:
                pass
            if attempt == retries:
                raise HTTPException(503, f"{service} is not available")

    @app.get("/api/photos/{photo_id}")
    def photo(photo_id: int, request: Request) -> dict:
        user(request)
        return get("photos", f"/photos/{photo_id}")

    @app.get("/api/photos/{photo_id}/keywords")
    def keywords(photo_id: int, request: Request) -> dict:
        user(request)
        return get("keywords", f"/keywords/{photo_id}")

    @app.get("/api/search")
    def search(q: str, request: Request, bundle: bool = True) -> dict:
        uid = user(request)
        start = time.perf_counter()
        ids = get("search", f"/search?q={q}&user_id={uid}")
        if bundle:  # one call for all photos
            found = get("photos", f"/photos?ids={','.join(map(str, ids))}") if ids else []
        else:  # one call per photo
            found = [get("photos", f"/photos/{i}") for i in ids]
        ms = (time.perf_counter() - start) * 1000
        return {"query": q, "photos": found, "calls": 1 + (1 if bundle else len(ids)), "ms": ms}

    return app


SERVICES = {
    "photos": photos_service,
    "keywords": keywords_service,
    "search": search_service,
    "gateway": gateway,
}

if __name__ == "__main__":
    uvicorn.run(SERVICES[sys.argv[1]](), host="0.0.0.0", port=8000, log_level="warning")
