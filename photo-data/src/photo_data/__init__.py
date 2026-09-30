"""Synthetic dataset for the photo service case study (a small Google Photos).

All tables and logs are generated on first use (deterministic) and cached in `data/`.
"""

import json
import os
from pathlib import Path

import pandas as pd

DATA_DIR = Path(os.environ.get("PHOTO_DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
VERSION = "1"
TABLES = [
    "users",
    "cameras",
    "photos",
    "albums",
    "album_photos",
    "album_followers",
    "friendships",
    "devices",
]


def ensure(force: bool = False) -> Path:
    stamp = DATA_DIR / f"VERSION-{VERSION}"
    if force or not stamp.exists():
        from . import generate, logs

        tables = generate.build()
        (DATA_DIR / "tables").mkdir(parents=True, exist_ok=True)
        (DATA_DIR / "truth").mkdir(parents=True, exist_ok=True)
        for name in TABLES:
            tables[name].to_parquet(DATA_DIR / "tables" / f"{name}.parquet", index=False)
            _csv(tables[name], DATA_DIR / "tables" / f"{name}.csv")
        _csv(tables["failed_uploads"], DATA_DIR / "truth" / "failed_uploads.csv")
        truth = logs.build(tables, DATA_DIR / "logs")
        (DATA_DIR / "truth" / "incidents.json").write_text(json.dumps(truth, indent=2) + "\n")
        export_preview()
        stamp.touch()
    return DATA_DIR


def _fmt(s: pd.Series) -> pd.Series:
    if not isinstance(s.dtype, pd.DatetimeTZDtype):
        return s
    if (s.dropna() == s.dropna().dt.normalize()).all():
        return s.dt.strftime("%Y-%m-%d")
    ms = (s.dt.microsecond // 1000).astype(str).str.zfill(3)
    return s.dt.strftime("%Y-%m-%dT%H:%M:%S.") + ms + "Z"


def _csv(df: pd.DataFrame, path: Path) -> None:
    df.apply(_fmt).to_csv(path, index=False)


PREVIEW_DAY = "2021-12-03"


def export_preview(lines: int = 300) -> None:
    """Files small enough for the table view of GitHub: small tables in full, the photos of one
    day, and the first lines of each log file."""
    preview = DATA_DIR / "preview"
    preview.mkdir(exist_ok=True)
    for f in preview.iterdir():
        f.unlink()
    for name in TABLES:
        df = pd.read_csv(DATA_DIR / "tables" / f"{name}.csv", dtype=str, keep_default_na=False)
        if name == "photos":
            df = df[df.upload_date.str.startswith(PREVIEW_DAY)]
            name += f"_{PREVIEW_DAY}"
        elif len(df) > 2000:
            continue
        df.to_csv(preview / f"{name}.csv", index=False)
    for log in sorted((DATA_DIR / "logs").rglob("*.*")):
        head = log.read_text().splitlines()[:lines]
        (preview / f"{log.parent.name}_{log.name}").write_text("".join(h + "\n" for h in head))


def _table(name: str):
    def load() -> pd.DataFrame:
        return pd.read_parquet(ensure() / "tables" / f"{name}.parquet")

    load.__name__ = name
    load.__doc__ = f"The `{name}` table."
    return load


users = _table("users")
cameras = _table("cameras")
photos = _table("photos")
albums = _table("albums")
album_photos = _table("album_photos")
album_followers = _table("album_followers")
friendships = _table("friendships")
devices = _table("devices")


def path(*parts: str) -> Path:
    """Path of a generated file, e.g. path("logs", "web", "access-web-1.log")."""
    return ensure().joinpath(*parts)


def access_logs() -> list[Path]:
    """The nginx access logs of the four web servers (3 days, combined log format)."""
    return sorted((ensure() / "logs" / "web").glob("access-*.log"))


def incidents() -> dict:
    """What really happened in the logs (the ground truth)."""
    return json.loads((ensure() / "truth" / "incidents.json").read_text())


def failed_uploads() -> pd.DataFrame:
    return pd.read_csv(ensure() / "truth" / "failed_uploads.csv", parse_dates=["time"])
