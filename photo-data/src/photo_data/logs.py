"""Generate the log files of the photo service for three days (2021-12-06 to 2021-12-08).

- `web/access-web-N.log`: nginx access logs of 4 web servers (combined log format)
- `web/error-web-N.log`: nginx error logs
- `services/upload.jsonl`, `services/thumbnailer.log`: logs of two back-end services
- `ops/deploy.log`, `ops/auth.log`, `ops/cron.log`: deployments, logins, nightly jobs
- `mobile/crashes.jsonl`: crash reports of the mobile apps

Two incidents are hidden in the logs (see `truth/incidents.json`).
"""

import hashlib
import json

import numpy as np
import pandas as pd

from .generate import CAM, INCIDENT, OBJECTS, REGIONS

LOG_DAYS = pd.date_range("2021-12-06", periods=3, freq="D", tz="UTC")
SERVERS = [f"web-{i}" for i in range(1, 5)]
REQUESTS_PER_DAY = 16_000
ATTACK = (pd.Timestamp("2021-12-08T03:05:12Z"), pd.Timestamp("2021-12-08T03:24:40Z"))
ATTACKER_IP = "203.0.113.77"
STATIC = ["/main.css", "/js/app.3f9a1c.js", "/favicon.ico", "/img/logo.svg"]
BOT_PATHS = ["/wp-login.php", "/.env", "/admin", "/phpmyadmin/", "/.git/config", "/xmlrpc.php"]
BROWSERS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/96.0.4664.45 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/15.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:94.0) Gecko/20100101 Firefox/94.0",
]
HOST = "photos.example.com"
BOT_UA = "Mozilla/5.0 (compatible; scanbot/2.1)"
SCRIPT_UA = "python-requests/2.26.0"


def build(tables: dict[str, pd.DataFrame], out, seed: int = 7) -> dict:
    rng = np.random.default_rng(seed)
    users, photos, devices = tables["users"], tables["photos"], tables["devices"]
    ctx = _context(rng, users, photos, devices, tables)
    requests = pd.concat(
        [_browsing(rng, ctx, day) for day in LOG_DAYS]
        + [_uploads(rng, ctx, photos, tables["failed_uploads"]), _attack(rng, ctx)],
        ignore_index=True,
    ).sort_values("time", kind="stable")
    requests["server"] = rng.choice(SERVERS, len(requests))
    for d in ("web", "services", "ops", "mobile"):
        (out / d).mkdir(parents=True, exist_ok=True)
    for s in SERVERS:
        r = requests[requests.server == s]
        _write(out / "web" / f"access-{s}.log", [_access_line(x) for x in r.itertuples()])
        _write(out / "web" / f"error-{s}.log", _error_lines(rng, r))
    upload_lines, thumb_lines = _service_logs(rng, requests, ctx)
    _write(out / "services" / "upload.jsonl", upload_lines)
    _write(out / "services" / "thumbnailer.log", thumb_lines)
    _write(out / "ops" / "deploy.log", _deploy_lines())
    _write(out / "ops" / "auth.log", _auth_lines(requests))
    _write(out / "ops" / "cron.log", _cron_lines(rng, requests))
    crashes = _crash_lines(rng, requests, ctx)
    _write(out / "mobile" / "crashes.jsonl", crashes)
    return _truth(requests, crashes)


def _context(rng, users, photos, devices, tables) -> dict:
    ips = [f"192.0.2.{i}" for i in range(1, 255)] + [f"198.51.100.{i}" for i in range(1, 255)]
    dev = devices.set_index("user_id")
    agents = {}
    for u in users.user_id:
        d = dev.loc[u]
        cam = CAM[d.phone_id]
        os_name = "iOS 15.1" if d.os == "ios" else "Android 12"
        agents[u] = (
            f"PhotosApp/{d.app_version} ({os_name}; {cam[2]})",
            BROWSERS[int(rng.integers(len(BROWSERS)))],
        )
    followers = tables["album_followers"].groupby("album_id").size()
    in_album = tables["album_photos"].assign(f=lambda x: x.album_id.map(followers).fillna(0))
    popularity = in_album.groupby("photo_id").f.max().reindex(photos.photo_id).fillna(0)
    friends: dict[int, list[int]] = {u: [] for u in users.user_id}
    fr = tables["friendships"]
    for a, b in zip(fr.user_id, fr.friend_id, strict=True):
        friends[a].append(b)
        friends[b].append(a)
    return {
        "users": users.set_index("user_id"),
        "ip": dict(zip(users.user_id, rng.choice(ips, len(users), replace=False), strict=True)),
        "agents": agents,
        "devices": dev,
        "photos": photos.set_index("photo_id"),
        "popularity": popularity.to_numpy(),
        "friends": friends,
        "albums": tables["album_followers"].groupby("user_id").album_id.apply(list).to_dict(),
        "own_albums": tables["albums"].groupby("owner_id").album_id.apply(list).to_dict(),
    }


def _times(rng, day, regions) -> pd.DatetimeIndex:
    local = rng.normal(15, 4.5, len(regions)) % 24
    offset = np.array([REGIONS[r] for r in regions])
    ms = ((local - offset) % 24 * 3_600_000).astype(np.int64)
    return pd.to_datetime(int(day.timestamp() * 1000) + ms, unit="ms", utc=True)


def _browsing(rng, ctx, day) -> pd.DataFrame:
    users, photos = ctx["users"], ctx["photos"]
    before = photos[photos.upload_date < day]
    age = (day - before.upload_date).dt.days.to_numpy()
    pop = ctx["popularity"][: len(before)]
    w = np.exp(-age / 12) * (1 + pop) ** 1.3 * rng.lognormal(0, 1, len(before))
    ids, owner = before.index.to_numpy(), before.user_id.to_numpy()
    by_user = {u: ids[owner == u][-200:] for u in users.index}
    n = int(REQUESTS_PER_DAY * rng.uniform(0.9, 1.1))
    activity = users.photos_total.to_numpy() ** 0.6
    who = rng.choice(users.index.to_numpy(), n, p=activity / activity.sum())
    kinds = rng.choice(
        ["view", "thumb", "static", "search", "album", "login", "bot", "list"],
        n,
        p=[0.58, 0.16, 0.1, 0.05, 0.04, 0.02, 0.01, 0.04],
    )
    popular = rng.choice(ids, n, p=w / w.sum())
    rows = []
    times = _times(rng, day, users.region.loc[who].to_numpy())
    for u, kind, pop_id, t in zip(who, kinds, popular, times, strict=True):
        app, browser = ctx["agents"][u]
        ua = app if rng.random() < 0.55 else browser
        row = {
            "time": t,
            "ip": ctx["ip"][u],
            "user": users.at[u, "account_name"],
            "method": "GET",
            "status": 200,
            "bytes": 0,
            "ua": ua,
            "user_id": u,
        }
        if kind in ("view", "thumb"):
            r = rng.random()
            if r < 0.35 and len(by_user[u]):
                pid = rng.choice(by_user[u])
            elif r < 0.6 and ctx["friends"][u]:
                f = rng.choice(ctx["friends"][u])
                pid = rng.choice(by_user[f]) if len(by_user[f]) else pop_id
            else:
                pid = pop_id
            path = photos.at[pid, "path"]
            if kind == "thumb":
                row |= {"path": f"/th{path}?w=256", "bytes": int(rng.integers(9_000, 30_000))}
            elif rng.random() < 0.2:
                row |= {"path": path, "status": 304}
            else:
                row |= {"path": path, "bytes": int(photos.at[pid, "size"] * 1_048_576)}
        elif kind == "static":
            row |= {
                "path": rng.choice(STATIC),
                "status": int(rng.choice([200, 304])),
                "ua": browser,
            }
            row["bytes"] = int(rng.integers(900, 90_000)) if row["status"] == 200 else 0
        elif kind == "search":
            q = rng.choice(list(OBJECTS)).replace(" ", "+")
            row |= {"path": f"/api/search?q={q}", "bytes": int(rng.integers(800, 12_000))}
        elif kind == "album":
            albums = ctx["albums"].get(u, []) + ctx["own_albums"].get(u, [])
            a = rng.choice(albums) if albums else 7001 + int(rng.integers(0, 50))
            row |= {"path": f"/api/albums/{a}", "bytes": int(rng.integers(2_000, 40_000))}
        elif kind == "list":
            row |= {"path": f"/api/photos?user={u}&page={int(rng.integers(1, 4))}"}
            row["bytes"] = int(rng.integers(4_000, 60_000))
        elif kind == "login":
            ok = rng.random() > 0.06
            row |= {"path": "/login", "method": "POST", "status": 200 if ok else 401, "user": "-"}
            row |= {"bytes": 312 if ok else 95, "login_user": users.at[u, "account_name"]}
        else:
            ip = f"203.0.113.{int(rng.integers(1, 60))}"
            row |= {
                "path": rng.choice(BOT_PATHS),
                "status": 404,
                "bytes": 153,
                "user": "-",
                "ip": ip,
                "ua": BOT_UA,
                "user_id": 0,
            }
        if row["status"] == 200 and rng.random() < 0.0005:
            row |= {"status": 500, "bytes": 177}
        rows.append(row)
    return pd.DataFrame(rows)


def _uploads(rng, ctx, photos, failed) -> pd.DataFrame:
    users, dev = ctx["users"], ctx["devices"]
    day = photos.upload_date.dt.normalize()
    ok = photos[day.isin(LOG_DAYS)]
    rows = []
    for p in ok.itertuples():
        via_app = p.camera_id is pd.NA or CAM[int(p.camera_id)][3] != "camera"
        rows.append(
            {
                "time": p.upload_date,
                "ip": ctx["ip"][p.user_id],
                "method": "POST",
                "user": users.at[p.user_id, "account_name"],
                "path": "/api/upload",
                "status": 201,
                "bytes": 184,
                "user_id": p.user_id,
                "photo_id": p.photo_id,
                "format": p.format,
                "size": p.size,
                "ua": ctx["agents"][p.user_id][0 if via_app else 1],
            }
        )
    for f in failed.itertuples():
        p = photos.loc[photos.photo_id == f.photo_id].iloc[0]
        rows.append(
            {
                "time": f.time,
                "ip": ctx["ip"][f.user_id],
                "method": "POST",
                "user": users.at[f.user_id, "account_name"],
                "path": "/api/upload",
                "status": 502,
                "bytes": 157,
                "user_id": f.user_id,
                "photo_id": f.photo_id,
                "format": p["format"],
                "size": p["size"],
                "attempt": f.attempt,
                "ua": ctx["agents"][f.user_id][0],
            }
        )
    assert (dev.loc[failed.user_id, "os"] == "ios").all()
    return pd.DataFrame(rows)


def _attack(rng, ctx) -> pd.DataFrame:
    """Credential stuffing: one address tries many account names, most do not exist."""
    names = list(ctx["users"].account_name.sample(25, random_state=3))
    leaked = [
        f"{a}{b}"
        for a in ("john", "mike", "sarah", "admin", "test", "info")
        for b in ("", "1", "123", ".smith", "_2020", "88", ".k", "x")
    ]
    candidates = names + leaked
    n = 190
    t = ATTACK[0] + pd.to_timedelta(np.sort(rng.integers(0, 1_168_000, n)), unit="ms")
    t = t.append(pd.DatetimeIndex([ATTACK[1]]))
    rows = [
        {
            "time": x,
            "ip": ATTACKER_IP,
            "user": "-",
            "method": "POST",
            "path": "/login",
            "status": 401,
            "bytes": 95,
            "ua": SCRIPT_UA,
            "user_id": 0,
            "login_user": candidates[int(rng.integers(len(candidates)))],
        }
        for x in t[:-1]
    ]
    rows.append(
        {
            "time": t[-1],
            "ip": ATTACKER_IP,
            "user": "-",
            "method": "POST",
            "path": "/login",
            "status": 429,
            "bytes": 88,
            "ua": SCRIPT_UA,
            "user_id": 0,
            "login_user": "admin",
        }
    )
    return pd.DataFrame(rows)


def _access_line(r) -> str:
    ts = r.time.strftime("%d/%b/%Y:%H:%M:%S +0000")
    ref = f"https://{HOST}/" if r.ua in BROWSERS else "-"
    return (
        f'{r.ip} - {r.user} [{ts}] "{r.method} {r.path} HTTP/1.1" {r.status} {r.bytes} '
        f'"{ref}" "{r.ua}"'
    )


def _error_lines(rng, r) -> list[str]:
    lines = []
    for x in r[r.status >= 500].itertuples():
        ts = x.time.strftime("%Y/%m/%d %H:%M:%S")
        conn = int(rng.integers(10_000, 99_999))
        what = (
            "upstream prematurely closed connection while reading response header from upstream"
            if x.status == 502
            else "upstream sent invalid header while reading response header from upstream"
        )
        up = "10.0.2.14:8000" if x.path == "/api/upload" else "10.0.2.21:8080"
        lines.append(
            f"{ts} [error] 31#31: *{conn} {what}, client: {x.ip}, server: {HOST}, "
            f'request: "{x.method} {x.path} HTTP/1.1", upstream: "http://{up}{x.path}", '
            f'host: "{HOST}"'
        )
    for x in r[(r.bytes > 8_000_000)].itertuples():
        ts = x.time.strftime("%Y/%m/%d %H:%M:%S")
        lines.append(
            f"{ts} [warn] 31#31: *{int(rng.integers(10_000, 99_999))} an upstream response is "
            f"buffered to a temporary file /var/cache/nginx/proxy_temp/{int(rng.integers(1, 9))}"
            f"/00/00000{int(rng.integers(1000, 9999))} while reading upstream, client: {x.ip}, "
            f'server: {HOST}, request: "GET {x.path} HTTP/1.1"'
        )
    return sorted(lines)


def _iso(t: pd.Timestamp) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def _service_logs(rng, requests, ctx) -> tuple[list[str], list[str]]:
    up, th = [], []
    deploy_end, rollback = INCIDENT
    for r in requests[requests.path == "/api/upload"].itertuples():
        inst = f"upload-{int(rng.integers(1, 4))}"
        client = r.ua.split(" ")[0].replace("PhotosApp/", "ios/" if "iOS" in r.ua else "android/")
        client = "web" if r.ua in BROWSERS else client
        base = {"ts": _iso(r.time), "level": "INFO", "service": "upload", "instance": inst}
        up.append(
            json.dumps(
                base
                | {
                    "event": "upload_received",
                    "user_id": int(r.user_id),
                    "format": r.format,
                    "bytes": int(r.size * 1_048_576),
                    "client": client,
                }
            )
        )
        t1 = r.time + pd.Timedelta(milliseconds=int(rng.integers(30, 400)))
        worker = f"thumbnailer-{int(rng.integers(1, 3))}"
        stamp = t1.strftime("%Y-%m-%d %H:%M:%S,") + f"{t1.microsecond // 1000:03d}"
        if r.status == 502:
            th.append(
                f"{stamp} ERROR [{worker}] cannot decode image format=heic "
                f"bytes={int(r.size * 1_048_576)}: cannot identify image file "
                f"<_io.BytesIO object at 0x7f3a{int(rng.integers(0x1000, 0xFFFF)):04x}>"
            )
            up.append(
                json.dumps(
                    base
                    | {
                        "ts": _iso(t1),
                        "level": "ERROR",
                        "event": "thumbnail_failed",
                        "user_id": int(r.user_id),
                        "error": "ThumbnailError: thumbnailer returned 500",
                    }
                )
            )
            up.append(
                json.dumps(
                    base
                    | {
                        "ts": _iso(t1),
                        "level": "CRITICAL",
                        "event": "worker_crashed",
                        "error": "unhandled ThumbnailError",
                    }
                )
            )
        else:
            ms = int(rng.lognormal(np.log(60 if r.format == "heic" else 35), 0.4))
            th.append(
                f"{stamp} INFO [{worker}] thumbnail created photo={int(r.photo_id)} "
                f"format={r.format} sizes=256,1024 ms={ms}"
            )
            up.append(
                json.dumps(
                    base
                    | {
                        "ts": _iso(t1),
                        "event": "upload_stored",
                        "photo_id": int(r.photo_id),
                        "path": ctx["photos"].at[int(r.photo_id), "path"],
                        "ms": ms + int(rng.integers(20, 90)),
                    }
                )
            )
            total = ctx["users"].at[r.user_id, "photos_total"]
            if total > 5000:
                up.append(
                    json.dumps(
                        base
                        | {
                            "ts": _iso(t1),
                            "level": "WARNING",
                            "event": "quota_warning",
                            "user_id": int(r.user_id),
                            "photos": int(total),
                            "quota": 5500,
                        }
                    )
                )
    for when, version, heif in [
        (pd.Timestamp("2021-12-06T00:00:00Z"), "2.7.3", "pillow-heif 0.1.4"),
        (deploy_end - pd.Timedelta(seconds=20), "2.8.0", "pillow-heif not installed"),
        (rollback - pd.Timedelta(seconds=25), "2.7.3", "pillow-heif 0.1.4"),
    ]:
        for w in (1, 2):
            stamp = when.strftime("%Y-%m-%d %H:%M:%S,") + f"{w * 111:03d}"
            th.append(
                f"{stamp} INFO [thumbnailer-{w}] starting thumbnailer {version} "
                f"(pillow 8.4.0, {heif})"
            )
    return sorted(up, key=lambda s: json.loads(s)["ts"]), sorted(th)


def _deploy_lines() -> list[str]:
    deploys = [
        ("2021-12-06T10:12:03Z", "search", "3.1.0", "a41b9e2", "ci", "deploy"),
        ("2021-12-06T16:40:27Z", "web-frontend", "2021.12.06", "77c01fd", "ci", "deploy"),
        ("2021-12-07T15:51:58Z", "thumbnailer", "2.8.0", "3fa9c1e", "ci", "deploy"),
        ("2021-12-07T23:03:23Z", "thumbnailer", "2.7.3", "d02e4b8", "oncall-maria", "rollback"),
        ("2021-12-08T11:05:44Z", "upload", "4.2.1", "9be3a70", "ci", "deploy"),
    ]
    lines = []
    for t, svc, ver, commit, actor, kind in deploys:
        start = pd.Timestamp(t)
        end = start + pd.Timedelta(seconds=42)
        lines.append(
            f'time={t} level=info msg="{kind} started" service={svc} version={ver} '
            f"commit={commit} actor={actor}"
        )
        lines.append(
            f'time={end.strftime("%Y-%m-%dT%H:%M:%SZ")} level=info msg="{kind} '
            f'finished" service={svc} version={ver} instances=2 duration_s=42'
        )
    return lines


def _auth_lines(requests) -> list[str]:
    lines = []
    known = set(requests.user[requests.user != "-"])
    for r in requests[requests.path == "/login"].itertuples():
        ts = r.time.strftime("%b %e %H:%M:%S")
        pid = 2211 if r.time.day != 8 else 2304
        if r.status == 200:
            what = f"accepted login user={r.login_user} ip={r.ip}"
        elif r.status == 429:
            what = f"rate limit exceeded, blocking ip={r.ip} for 3600s"
        else:
            reason = "bad_password" if r.login_user in known else "unknown_user"
            what = f"login failed user={r.login_user} ip={r.ip} reason={reason}"
        lines.append(f"{ts} auth-1 photos-auth[{pid}]: {what}")
    return lines


def _cron_lines(rng, requests) -> list[str]:
    lines = []
    for day in LOG_DAYS:
        for hh, job in [("02:00", "view_counts"), ("03:30", "reindex_search"), ("04:15", "backup")]:
            t = pd.Timestamp(f"{day.date()}T{hh}:01Z")
            ts = t.strftime("%b %e %H:%M:%S")
            lines.append(
                f"{ts} batch-1 CRON[{int(rng.integers(4000, 9000))}]: (photos) CMD "
                f"(/opt/jobs/{job}.sh)"
            )
            dur = int(rng.integers(200, 900))
            done = (t + pd.Timedelta(seconds=dur)).strftime("%b %e %H:%M:%S")
            lines.append(
                f"{done} batch-1 {job}[{int(rng.integers(4000, 9000))}]: finished "
                f"status=ok duration={dur}s"
            )
    return sorted(lines, key=lambda s: pd.Timestamp("2021 " + s[:15]))


def _crash_lines(rng, requests, ctx) -> list[str]:
    background = [
        ("android", "java.lang.NullPointerException", "AlbumAdapter.onBindViewHolder", "Albums"),
        ("android", "java.lang.OutOfMemoryError", "BitmapFactory.decodeStream", "Viewer"),
        ("ios", "EXC_BAD_ACCESS", "ImageCache.evict", "Library"),
        ("ios", "NSInternalInconsistencyException", "GridLayout.prepare", "Library"),
    ]
    users = ctx["users"].index.to_numpy()
    rows = []
    for day in LOG_DAYS:
        for _ in range(int(rng.integers(35, 50))):
            platform, exc, where, screen = background[int(rng.integers(len(background)))]
            u = users[int(rng.integers(len(users)))]
            t = day + pd.Timedelta(milliseconds=int(rng.integers(0, 86_400_000)))
            rows.append((t, platform, exc, where, screen, u))
    for r in requests[requests.status == 502].itertuples():
        if r.path == "/api/upload" and rng.random() < 0.6:
            t = r.time + pd.Timedelta(milliseconds=int(rng.integers(200, 2000)))
            rows.append(
                (
                    t,
                    "ios",
                    "Fatal error",
                    "Unexpectedly found nil while unwrapping an "
                    "Optional value in UploadResponse.decode",
                    "UploadQueue",
                    r.user_id,
                )
            )
    lines = []
    for t, platform, exc, where, screen, u in sorted(rows, key=lambda x: x[0]):
        d = ctx["devices"].loc[u]
        device = (
            CAM[d.phone_id][2]
            if d.os == platform
            else ("Pixel 6" if platform == "android" else "iPhone 12")
        )
        lines.append(
            json.dumps(
                {
                    "received": _iso(t),
                    "platform": platform,
                    "app_version": "5.2.0" if platform == "android" else "7.4.1",
                    "os": "Android 12" if platform == "android" else "iOS 15.1",
                    "device": device,
                    "exception": exc,
                    "location": where,
                    "screen": screen,
                    "user": hashlib.sha256(str(u).encode()).hexdigest()[:12],
                }
            )
        )
    return lines


def _truth(requests, crashes) -> dict:
    up = requests[(requests.path == "/api/upload") & (requests.status == 502)]
    login = requests[(requests.ip == ATTACKER_IP)]
    n_crash = sum(1 for c in crashes if "UploadResponse" in c)
    return {
        "incidents": [
            {
                "id": "thumbnailer-heic",
                "start": _iso(INCIDENT[0]),
                "end": _iso(INCIDENT[1]),
                "cause": "thumbnailer 2.8.0 was deployed without HEIC support (pillow-heif not "
                "installed); the upload service crashed on each HEIC upload; rollback to 2.7.3",
                "failed_upload_requests": int(len(up)),
                "affected_users": int(up.user_id.nunique()),
                "ios_crashes": n_crash,
            },
            {
                "id": "credential-stuffing",
                "start": _iso(ATTACK[0]),
                "end": _iso(ATTACK[1]),
                "cause": f"one address ({ATTACKER_IP}) tried many account names; blocked by "
                "the rate limit",
                "failed_logins": int((login.status == 401).sum()),
            },
        ]
    }


def _write(path, lines) -> None:
    path.write_text("".join(line + "\n" for line in lines))
