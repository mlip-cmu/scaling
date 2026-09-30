import json

import pandas as pd

import photo_data as d
from photo_data import generate


def test_generator_is_deterministic():
    a, b = generate.build(seed=5), generate.build(seed=5)
    pd.testing.assert_frame_equal(a["photos"], b["photos"])


def test_slide_rows_are_present():
    p = d.photos().set_index("photo_id")
    assert p.at[133422131, "path"] == "/st/u211/1U6uFl47Fy.jpg"
    assert p.at[133422132, "user_id"] == 13221
    assert list(p.loc[133422131:133422133, "size"]) == [5.7, 3.1, 4.8]
    u = d.users().set_index("account_name")
    assert u.at["ckaestne", "user_id"] == 54351 and u.at["ckaestne", "photos_total"] == 5124
    assert u.at["eva.burk", "photos_total"] == 3
    assert d.cameras().set_index("camera_id").at[663, "print_name"] == "Google Pixel 5"


def test_keys_and_references():
    users, photos = d.users(), d.photos()
    assert users.user_id.is_unique and photos.photo_id.is_unique and photos.path.is_unique
    assert set(photos.user_id) <= set(users.user_id)
    counts = photos.user_id.value_counts()
    assert (users.photos_total.to_numpy() == counts.loc[users.user_id].to_numpy()).all()
    assert photos.upload_date.is_monotonic_increasing
    assert set(d.album_photos().photo_id) <= set(photos.photo_id)
    assert set(d.album_followers().user_id) <= set(users.user_id)
    f = d.friendships()
    assert (f.user_id != f.friend_id).all()
    assert not f.duplicated(["user_id", "friend_id"]).any()


def test_logs_match_tables_and_truth():
    paths = set(d.photos().path)
    lines = [line for f in d.access_logs() for line in f.read_text().splitlines()]
    views = [line.split()[6] for line in lines if '"GET /st/' in line]
    assert views and set(views) <= paths
    failed = [line for line in lines if "POST /api/upload" in line and '" 502 ' in line]
    truth = d.incidents()["incidents"][0]
    assert len(failed) == truth["failed_upload_requests"] == len(d.failed_uploads())
    crashes = d.path("logs", "mobile", "crashes.jsonl").read_text().splitlines()
    assert (
        sum("UploadResponse" in json.loads(c)["location"] for c in crashes) == truth["ios_crashes"]
    )
