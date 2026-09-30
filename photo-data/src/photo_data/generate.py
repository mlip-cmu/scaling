"""Generate the tables of the photo service (deterministic for a given seed)."""

import string

import numpy as np
import pandas as pd

from .names import (
    ALBUM_TITLES,
    APP_VERSION,
    CAMERAS,
    FIRST,
    LAST,
    OBJECTS,
    PRO_CAMERAS,
    REGION_SHARE,
    REGIONS,
    SEASON,
    SLIDE_PHOTOS,
    SLIDE_USERS,
    TITLES,
)

SEED = 12
START, END = pd.Timestamp("2021-07-01", tz="UTC"), pd.Timestamp("2022-01-01", tz="UTC")
N_USERS, N_PHOTOS = 300, 40_000
# On this day, a new version of the thumbnail service cannot decode HEIC images (see logs.py).
INCIDENT = (pd.Timestamp("2021-12-07T15:52:40Z"), pd.Timestamp("2021-12-07T23:04:05Z"))
HOLIDAYS = {
    "2021-07-04": 3.0,
    "2021-07-05": 1.6,
    "2021-09-06": 1.5,
    "2021-10-31": 1.8,
    "2021-11-25": 2.5,
    "2021-11-26": 1.8,
    "2021-12-24": 2.5,
    "2021-12-25": 3.5,
    "2021-12-26": 2.0,
    "2021-12-31": 3.0,
}
LAST_LOGIN = {u[0]: pd.Timestamp(u[4]) for u in SLIDE_USERS}
BASE62 = string.digits + string.ascii_letters
CAM = {c[0]: c for c in CAMERAS}


def build(seed: int = SEED) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    users = _users(rng)
    friendships = _friendships(rng, users)
    devices = _devices(rng, users)
    photos, failed = _photos(rng, users, devices, friendships)
    users["photos_total"] = users.user_id.map(photos.user_id.value_counts()).astype(int)
    users["last_login"] = _last_login(rng, users, photos)
    albums, album_photos, followers = _albums(rng, users, photos, friendships)
    cameras = pd.DataFrame(
        [(c[0], c[1], c[2]) for c in CAMERAS], columns=["camera_id", "manufacturer", "print_name"]
    )
    return {
        "users": users,
        "cameras": cameras,
        "photos": photos,
        "albums": albums,
        "album_photos": album_photos,
        "album_followers": followers,
        "friendships": friendships,
        "devices": devices,
        "failed_uploads": failed,
    }


def _users(rng) -> pd.DataFrame:
    ids = rng.choice(np.arange(10_000, 100_000), N_USERS, replace=False)
    ids[:2] = [u[0] for u in SLIDE_USERS]
    names, taken = [], {u[1] for u in SLIDE_USERS}
    for _ in range(N_USERS - 2):
        while True:
            f, last = rng.choice(FIRST), rng.choice(LAST)
            style = rng.integers(4)
            name = [f"{f}.{last}", f"{f[0]}{last}", f"{f}{last[0]}", f"{f}_{last}"][style]
            if rng.random() < 0.2:
                name += str(rng.integers(1, 99))
            if name not in taken:
                taken.add(name)
                names.append(name)
                break
    regions = rng.choice(list(REGIONS), N_USERS, p=REGION_SHARE)
    signup = pd.Timestamp("2015-01-01", tz="UTC") + pd.to_timedelta(
        rng.integers(0, 6 * 365 + 180, N_USERS), unit="D"
    )
    df = pd.DataFrame(
        {
            "user_id": ids,
            "account_name": [u[1] for u in SLIDE_USERS] + names,
            "region": [u[2] for u in SLIDE_USERS] + list(regions[2:]),
            "signup_date": signup.normalize(),
        }
    )
    df.loc[0, "signup_date"] = pd.Timestamp("2016-03-14", tz="UTC")
    df.loc[1, "signup_date"] = pd.Timestamp("2021-11-28", tz="UTC")
    return df


def _friendships(rng, users) -> pd.DataFrame:
    n = len(users)
    degree = np.clip(rng.lognormal(np.log(7), 0.6, n), 1, 40)
    degree[0], degree[1] = 60, 2
    region = users.region.to_numpy()
    pairs: set[tuple[int, int]] = set()
    for i in range(n):
        need = int(round(degree[i])) - sum(1 for p in pairs if i in p)
        if need <= 0:
            continue
        w = degree * np.where(region == region[i], 4.0, 1.0)
        w[i] = 0
        if i != 1:
            w[1] = 0  # the new user has few friends
        for j in rng.choice(n, size=min(need, n - 2), replace=False, p=w / w.sum()):
            pairs.add((min(i, j), max(i, j)))
    if 1 not in {x for p in pairs for x in p}:
        pairs.add((0, 1))
    a, b = np.array(sorted(pairs)).T
    uid, signup = users.user_id.to_numpy(), users.signup_date
    later = np.maximum(signup.iloc[a].to_numpy(), signup.iloc[b].to_numpy())
    days = np.maximum((pd.Timestamp("2021-12-01", tz="UTC") - pd.DatetimeIndex(later)).days, 1)
    since = pd.DatetimeIndex(later) + pd.to_timedelta(rng.integers(0, days), unit="D")
    return pd.DataFrame({"user_id": uid[a], "friend_id": uid[b], "since": since.normalize()})


def _devices(rng, users) -> pd.DataFrame:
    phones = [c for c in CAMERAS if c[6] > 0]
    share = np.array([c[6] for c in phones])
    phone = rng.choice([c[0] for c in phones], len(users), p=share / share.sum())
    pro = np.where(rng.random(len(users)) < 0.12, rng.choice(PRO_CAMERAS, len(users)), 0)
    phone[:2], pro[:2] = [663, 1844], [8015, 0]
    kind = [CAM[p][3] for p in phone]
    heic = np.array([k == "ios" and rng.random() < 0.8 for k in kind])
    return pd.DataFrame(
        {
            "user_id": users.user_id,
            "phone_id": phone,
            "pro_camera_id": pro,
            "os": kind,
            "app_version": [APP_VERSION[k] for k in kind],
            "uses_heic": heic,
        }
    )


def _counts(rng, n_users: int) -> np.ndarray:
    fixed = [u[3] for u in SLIDE_USERS]
    raw = rng.lognormal(3.5, 1.1, n_users - 2)
    rest = np.maximum(1, np.round(raw / raw.sum() * (N_PHOTOS - sum(fixed)))).astype(int)
    rest[np.argmax(rest)] += N_PHOTOS - sum(fixed) - rest.sum()
    return np.concatenate([fixed, rest])


def _day_weights() -> tuple[pd.DatetimeIndex, np.ndarray]:
    days = pd.date_range(START, END - pd.Timedelta(days=1), freq="D")
    w = np.where(days.dayofweek >= 5, 1.4, 1.0) * np.where(days.month <= 8, 1.3, 1.0)
    w *= np.array([HOLIDAYS.get(str(d.date()), 1.0) for d in days])
    return days, w / w.sum()


def _session_times(rng, n: int, start, end, offset: int) -> pd.DatetimeIndex:
    """Upload times of n photos: sessions of a few photos, in the afternoon and evening."""
    if n == 0:
        return pd.DatetimeIndex([], tz="UTC")
    days, w = _day_weights()
    w = np.where((days >= start.normalize()) & (days < end.normalize()), w, 0)
    sizes = []
    while sum(sizes) < n:
        sizes.append(int(rng.geometric(0.3)))
    sizes[-1] -= sum(sizes) - n
    k = len(sizes)
    day = rng.choice(len(days), k, p=w / w.sum())
    hour = rng.normal(17, 3.5, k) % 24  # local time
    start_ms = (hour - offset) * 3_600_000
    t = np.repeat(days[day].as_unit("ms").asi8 + start_ms.astype(np.int64), sizes)
    t = t + rng.integers(0, 10 * 60_000, n)
    return pd.to_datetime(t, unit="ms", utc=True)


def _setting(rng, cam_id: int) -> str:
    _, _, _, kind, aperture, focal, _ = CAM[cam_id]
    shutter = rng.choice([15, 30, 60, 120, 250, 500, 1000, 2000, 4000])
    iso = int(np.clip(rng.lognormal(np.log(200), 0.9), 50, 6400))
    if kind == "camera":
        focal = float(rng.choice([24, 35, 50, 70, 85, 105, 200]))
        aperture = float(rng.choice([aperture, 2.8, 4.0, 5.6, 8.0]))
    return f"ƒ/{aperture:g}; 1/{shutter}; {focal:.2f}mm; ISO{iso}"


def _objects(rng, month: int, n_people: int) -> list[str]:
    names = list(OBJECTS)
    w = np.array([OBJECTS[o] * SEASON.get(o, {}).get(month, 1.0) for o in names])
    k = rng.choice([1, 2, 3, 4], p=[0.3, 0.35, 0.25, 0.1])
    objs = list(rng.choice(names, k, replace=False, p=w / w.sum()))
    if n_people and "person" not in objs:
        objs.insert(0, "person")
    if not n_people and "person" in objs and rng.random() < 0.5:
        objs.remove("person")
    return objs or ["sky"]


def _name(rng, k: int) -> str:
    return "".join(rng.choice(list(BASE62), k))


def _photos(rng, users, devices, friendships) -> tuple[pd.DataFrame, pd.DataFrame]:
    counts = _counts(rng, len(users))
    friends: dict[int, list[int]] = {u: [] for u in users.user_id}
    for a, b in zip(friendships.user_id, friendships.friend_id, strict=True):
        friends[a].append(b)
        friends[b].append(a)
    dev = devices.set_index("user_id")
    slide = {p[0]: p for p in SLIDE_PHOTOS}
    rows = []
    for u, n in zip(users.itertuples(), counts, strict=True):
        n_slide = sum(1 for p in SLIDE_PHOTOS if p[1] == u.user_id)
        end = LAST_LOGIN.get(u.user_id, END)
        times = _session_times(rng, n - n_slide, max(START, u.signup_date), end, REGIONS[u.region])
        d = dev.loc[u.user_id]
        for t in times:
            r = rng.random()
            if r < 0.02:
                cam = 0
            elif r < 0.15 and d.pro_camera_id:
                cam = d.pro_camera_id
            else:
                cam = d.phone_id
            rows.append({"user_id": u.user_id, "upload_date": t, "camera_id": cam})
    for p in SLIDE_PHOTOS:
        rows.append({"user_id": p[1], "upload_date": pd.Timestamp(p[3]), "camera_id": p[5]})
    df = pd.DataFrame(rows)
    # keep the three photos of the slide next to each other: no other upload in the same 50 ms
    window = (df.upload_date >= "2021-12-03T09:18:32.100Z") & (
        df.upload_date <= "2021-12-03T09:18:32.150Z"
    )
    is_slide = df.index >= len(df) - len(SLIDE_PHOTOS)
    df.loc[window & ~is_slide, "upload_date"] += pd.Timedelta(seconds=1)

    heic = df.user_id.map(dev.uses_heic) & df.camera_id.map(
        lambda c: c in CAM and CAM[c][3] == "ios"
    )
    heic &= rng.random(len(df)) < 0.85
    fmt = np.where(df.camera_id == 0, "png", np.where(heic, "heic", "jpg"))
    df["format"] = fmt
    df.loc[is_slide, "format"] = "jpg"
    failed = _incident(rng, df)

    df = df.sort_values("upload_date", kind="stable").reset_index(names="row")
    first = df.index[df.row == len(rows) - len(SLIDE_PHOTOS)][0]
    df.insert(0, "photo_id", 133422131 - first + df.index)
    failed["photo_id"] = failed.row.map(df.set_index("row").photo_id)

    paths, sizes, settings, titles, objects, people = [], [], [], [], [], []
    for r in df.itertuples():
        if r.photo_id in slide:
            p = slide[r.photo_id]
            paths.append(p[2])
            sizes.append(p[4])
            settings.append(p[6])
        else:
            shard = rng.choice(list("uuxyz")) + format(int(rng.integers(0x10, 0xFFF)), "x")
            paths.append(f"/st/{shard}/{_name(rng, 10)}.{r.format}")
            if r.camera_id == 0:
                size = rng.lognormal(np.log(1.0), 0.5)
            elif CAM[r.camera_id][3] == "camera":
                size = rng.lognormal(np.log(12), 0.3)
            else:
                size = rng.lognormal(np.log(3.6), 0.35) * (0.55 if r.format == "heic" else 1)
            sizes.append(round(max(size, 0.1), 1))
            settings.append(_setting(rng, r.camera_id) if r.camera_id else "")
        month = r.upload_date.month
        titles.append(rng.choice(TITLES) if rng.random() < 0.1 else "")
        fr = friends[r.user_id]
        k = 0 if not fr or r.camera_id == 0 or rng.random() > 0.35 else int(rng.integers(1, 4))
        ppl = list(rng.choice(fr, min(k, len(fr)), replace=False)) if k else []
        objects.append(";".join(_objects(rng, month, len(ppl)) if r.camera_id else ["text"]))
        people.append(";".join(str(x) for x in ppl))
    df["path"], df["size"], df["camera_setting"] = paths, sizes, settings
    df["title"], df["objects"], df["people"] = titles, objects, people
    df["camera_id"] = df.camera_id.astype("Int64").replace(0, pd.NA)
    cols = ["photo_id", "user_id", "path", "upload_date", "size", "camera_id", "camera_setting"]
    photos = df[cols + ["format", "title", "objects", "people"]]
    return photos, failed[["photo_id", "user_id", "attempt", "time"]]


def _incident(rng, df) -> pd.DataFrame:
    """HEIC uploads fail during the incident; clients retry and succeed after the rollback."""
    start, end = INCIDENT
    hit = df.index[(df.format == "heic") & (df.upload_date >= start) & (df.upload_date <= end)]
    attempts = []
    for i in hit:
        t = df.at[i, "upload_date"]
        for a, delay in enumerate([0, 30, 120, 600, 1800]):
            if t + pd.Timedelta(seconds=delay) > end:
                break
            attempts.append(
                {
                    "row": i,
                    "user_id": df.at[i, "user_id"],
                    "attempt": a + 1,
                    "time": t + pd.Timedelta(seconds=delay),
                }
            )
        df.at[i, "upload_date"] = end + pd.Timedelta(seconds=int(rng.integers(20, 900)))
    return pd.DataFrame(attempts, columns=["row", "user_id", "attempt", "time"])


def _last_login(rng, users, photos) -> pd.Series:
    last = users.user_id.map(photos.groupby("user_id").upload_date.max())
    login = last + pd.to_timedelta(rng.integers(0, 3 * 86_400_000, len(users)), unit="ms")
    login = login.clip(upper=pd.Timestamp("2021-12-31T23:59:59Z"))
    for i, u in enumerate(SLIDE_USERS):
        login.iloc[i] = pd.Timestamp(u[4])
    return login


def _albums(rng, users, photos, friendships):
    by_user = {u: g.sort_values("upload_date") for u, g in photos.groupby("user_id")}
    friends: dict[int, list[int]] = {u: [] for u in users.user_id}
    for a, b in zip(friendships.user_id, friendships.friend_id, strict=True):
        friends[a].append(b)
        friends[b].append(a)
    all_users = users.user_id.to_numpy()
    albums, members, followers = [], [], []
    for u in users.user_id:
        g = by_user[u]
        n = 24 if u == SLIDE_USERS[0][0] else (0 if len(g) < 5 else rng.poisson(0.9))
        for _ in range(n):
            size = int(min(len(g), rng.integers(5, 60)))
            s = int(rng.integers(0, len(g) - size + 1))
            part = g.iloc[s : s + size]
            shared = rng.random() < (0.5 if u == SLIDE_USERS[0][0] else 0.35)
            created = part.upload_date.max() + pd.Timedelta(minutes=int(rng.integers(5, 3000)))
            albums.append(
                {
                    "owner_id": u,
                    "title": rng.choice(ALBUM_TITLES),
                    "shared": shared,
                    "created": created,
                    "photos": part.photo_id.tolist(),
                }
            )
    albums.sort(key=lambda a: a["created"])
    for i, a in enumerate(albums):
        a["album_id"] = 7001 + i
        members += [(a["album_id"], p) for p in a.pop("photos")]
        if a["shared"]:
            mean = 25 if a["owner_id"] == SLIDE_USERS[0][0] else 5
            k = min(1 + int(rng.geometric(1 / mean)), 120)
            fr = [f for f in friends[a["owner_id"]] if rng.random() < 0.7]
            others = rng.choice(all_users, k, replace=False)
            chosen = list(dict.fromkeys(fr[:k] + [o for o in others if o != a["owner_id"]]))[:k]
            for f in chosen:
                since = a["created"] + pd.Timedelta(hours=int(rng.integers(1, 24 * 20)))
                followers.append((a["album_id"], f, since))
    cols = ["album_id", "owner_id", "title", "shared", "created"]
    return (
        pd.DataFrame(albums)[cols],
        pd.DataFrame(members, columns=["album_id", "photo_id"]),
        pd.DataFrame(followers, columns=["album_id", "user_id", "since"]),
    )
