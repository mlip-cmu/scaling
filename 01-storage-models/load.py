"""Load the same photo data into PostgreSQL (tables) and MongoDB (documents).

Start the databases first: `docker compose up -d`.
"""

from pathlib import Path

import pandas as pd
import psycopg
import pymongo

import photo_data

PG = "postgresql://photos:photos@localhost:5432/photos"
MONGO = "mongodb://localhost:27017"


def load_postgres() -> None:
    with psycopg.connect(PG) as con:
        con.execute(
            "DROP TABLE IF EXISTS album_followers, album_photos, albums, photos, cameras, users"
        )
        con.execute(Path("schema.sql").read_text())
        tables = {
            "users": photo_data.users()[
                ["user_id", "account_name", "region", "photos_total", "last_login"]
            ],
            "cameras": photo_data.cameras(),
            "photos": photo_data.photos()[
                [
                    "photo_id",
                    "user_id",
                    "path",
                    "upload_date",
                    "size",
                    "camera_id",
                    "camera_setting",
                    "title",
                ]
            ],
            "albums": photo_data.albums()[["album_id", "owner_id", "title", "shared"]],
            "album_photos": photo_data.album_photos(),
            "album_followers": photo_data.album_followers()[["album_id", "user_id"]],
        }
        for name, df in tables.items():
            with con.cursor().copy(f"COPY {name} ({', '.join(df.columns)}) FROM STDIN") as copy:
                for row in df.astype(object).where(df.notna(), None).itertuples(index=False):
                    copy.write_row(row)
        con.execute("ANALYZE")
        for name in tables:
            n = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
            print(f"   PostgreSQL table {name:<16} {n:>6} rows")


def documents() -> tuple[list[dict], list[dict]]:
    """Photos with the user and the camera inside; albums with lists of photos and followers."""
    users = photo_data.users().set_index("user_id")
    cams = photo_data.cameras().set_index("camera_id")
    photos = []
    for p in photo_data.photos().itertuples():
        doc = {
            "_id": int(p.photo_id),
            "path": p.path,
            "upload_date": p.upload_date,
            "user": {
                "account_name": users.at[p.user_id, "account_name"],
                "account_id": f"a/{p.user_id}",
            },
            "size": float(p.size),
            "title": p.title,
        }
        if not pd.isna(p.camera_id):
            c = cams.loc[int(p.camera_id)]
            doc["camera"] = {
                "manufacturer": c.manufacturer,
                "print_name": c.print_name,
                "settings": p.camera_setting,
            }
        photos.append(doc)
    members = photo_data.album_photos().groupby("album_id").photo_id.apply(list)
    followers = photo_data.album_followers().groupby("album_id").user_id.apply(list)
    albums = [
        {
            "_id": int(a.album_id),
            "title": a.title,
            "shared": bool(a.shared),
            "owner": {
                "account_name": users.at[a.owner_id, "account_name"],
                "account_id": f"a/{a.owner_id}",
            },
            "photos": [int(x) for x in members.get(a.album_id, [])],
            "followers": [f"a/{x}" for x in followers.get(a.album_id, [])],
        }
        for a in photo_data.albums().itertuples()
    ]
    return photos, albums


def load_mongo() -> None:
    db = pymongo.MongoClient(MONGO).photos
    db.photos.drop()
    db.albums.drop()
    photos, albums = documents()
    db.photos.insert_many(photos)
    db.albums.insert_many(albums)
    print(f"   MongoDB collection photos  {db.photos.count_documents({}):>6} documents")
    print(f"   MongoDB collection albums  {db.albums.count_documents({}):>6} documents")


if __name__ == "__main__":
    load_postgres()
    load_mongo()
