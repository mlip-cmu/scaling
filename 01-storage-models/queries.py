"""The same questions to tables, documents, and log files: what is easy, and what is hard.

Run `load.py` first.
"""

import json
import time

import psycopg
import pymongo

import photo_data

PG = "postgresql://photos:photos@localhost:5432/photos"
pg = psycopg.connect(PG, autocommit=True)
db = pymongo.MongoClient("mongodb://localhost:27017").photos


def timed(f):
    start = time.perf_counter()
    result = f()
    return result, (time.perf_counter() - start) * 1000


print("1. All photos of the user ckaestne")
sql = """SELECT p.photo_id, p.path, u.photos_total
         FROM photos p, users u
         WHERE u.user_id = p.user_id AND u.account_name = 'ckaestne'"""
rows, ms = timed(lambda: pg.execute(sql).fetchall())
print(f"   SQL, a join of 2 tables:         {len(rows)} rows in {ms:.1f} ms")
db.photos.drop_indexes()
docs, ms = timed(lambda: list(db.photos.find({"user.account_name": "ckaestne"})))
plan = db.photos.find({"user.account_name": "ckaestne"}).explain()["executionStats"]
print(
    f"   MongoDB, one collection:         {len(docs)} documents in {ms:.1f} ms "
    f"(read {plan['totalDocsExamined']} documents: no index)"
)
db.photos.create_index("user.account_name")
docs, ms = timed(lambda: list(db.photos.find({"user.account_name": "ckaestne"})))
plan = db.photos.find({"user.account_name": "ckaestne"}).explain()["executionStats"]
print(
    f"   MongoDB with an index:           {len(docs)} documents in {ms:.1f} ms "
    f"(read {plan['totalDocsExamined']} documents)"
)
print(f"   one document: {json.dumps(docs[0], default=str, ensure_ascii=False)}")
plan = pg.execute("EXPLAIN " + sql).fetchall()
print("   the SQL query says what, not how; the database plans how (EXPLAIN):")
for (line,) in plan[:4]:
    print(f"     {line}")

print("\n2. The user renames the account ckaestne to christian")
n = pg.execute("UPDATE users SET account_name = 'christian' WHERE account_name = 'ckaestne'")
print(f"   SQL: {n.rowcount} row changes (the name is stored once)")
r = db.photos.update_many(
    {"user.account_name": "ckaestne"}, {"$set": {"user.account_name": "christian"}}
)
r2 = db.albums.update_many(
    {"owner.account_name": "ckaestne"}, {"$set": {"owner.account_name": "christian"}}
)
print(
    f"   MongoDB: {r.modified_count} photos and {r2.modified_count} albums change "
    "(each document has a copy of the name)"
)
pg.execute("UPDATE users SET account_name = 'ckaestne' WHERE account_name = 'christian'")
db.photos.update_many(
    {"user.account_name": "christian"}, {"$set": {"user.account_name": "ckaestne"}}
)
db.albums.update_many(
    {"owner.account_name": "christian"}, {"$set": {"owner.account_name": "ckaestne"}}
)

print("\n3. Many-to-many: the photos in the albums that eva.burk follows")
sql = """SELECT DISTINCT p.photo_id FROM users u
         JOIN album_followers f ON f.user_id = u.user_id
         JOIN album_photos ap ON ap.album_id = f.album_id
         JOIN photos p ON p.photo_id = ap.photo_id
         WHERE u.account_name = 'eva.burk'"""
rows = {r[0] for r in pg.execute(sql).fetchall()}
eva = pg.execute("SELECT user_id FROM users WHERE account_name = 'eva.burk'").fetchone()[0]
albums = list(db.albums.find({"followers": f"a/{eva}"}, {"photos": 1}))
ids = {p for a in albums for p in a["photos"]}
found = {d["_id"] for d in db.photos.find({"_id": {"$in": list(ids)}}, {"_id": 1})}
print(f"   SQL: one query with 3 joins: {len(rows)} photos")
print(
    f"   MongoDB: first the user id, then the albums that the user follows ({len(albums)}), "
    "then the photos: "
    f"{len(found)} photos, the same: {found == rows}"
)

print("\n4. A new photo with a wrong value: size = '5.7 MB' (text instead of a number)")
try:
    pg.execute(
        "INSERT INTO photos (photo_id, user_id, path, upload_date, size) "
        "VALUES (1, 54351, '/st/x/1.jpg', now(), '5.7 MB')"
    )
except psycopg.Error as e:
    print(f"   PostgreSQL rejects it: {str(e).splitlines()[0]}")
db.photos.delete_many({"_id": {"$in": [1, 2]}})
db.photos.insert_one({"_id": 1, "path": "/st/x/1.jpg", "size": "5.7 MB"})
print("   MongoDB accepts it: the collection has no schema")
db.command(
    "collMod",
    "photos",
    validator={
        "$jsonSchema": {
            "required": ["path", "size"],
            "properties": {"size": {"bsonType": "double"}},
        }
    },
)
try:
    db.photos.insert_one({"_id": 2, "path": "/st/x/2.jpg", "size": "5.7 MB"})
except pymongo.errors.WriteError as e:
    print(f"   with an optional schema validator, MongoDB rejects it: {e.details['errmsg']}")
db.photos.delete_many({"_id": {"$in": [1, 2]}})
db.command("collMod", "photos", validator={})

print("\n5. Log files: how often was photo 133422131 viewed?")
path = pg.execute("SELECT path FROM photos WHERE photo_id = 133422131").fetchone()[0]


def grep() -> int:
    n = 0
    for f in photo_data.access_logs():
        for line in f.read_text().splitlines():
            if f'"GET {path} ' in line:
                n += 1
    return n


n, ms = timed(grep)
lines = sum(len(f.read_text().splitlines()) for f in photo_data.access_logs())
print(f"   search in the log files: {n} views; read all {lines} lines in {ms:.0f} ms")
print("   (appending a line is easy; there is no index, so each question reads everything)")
