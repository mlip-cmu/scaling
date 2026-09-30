# photo-data: the shared dataset

A synthetic, deterministic dataset of a small photo service like Google Photos. Users upload
photos with the mobile app or the web page. An ML model detects objects in each photo (for
the keyword search), and a second model finds friends in the photos. The data covers the
second half of 2021: 300 users, 40,000 photos, 20 camera models, shared albums, and three
days (2021-12-06 to 2021-12-08) of logs from all parts of the system.

Because the data is synthetic, the truth is known: each photo has its true `objects` and
`people` (what a perfect model would find), and `truth/` documents what happened in the
logs.

Every other project uses this package as a local path dependency. The data is generated on
first use (about 10 s) and cached in `data/`. The same data is committed as CSV and log
files, so you can look at it on GitHub. `data/preview/` has files that are small enough for
the table view of GitHub: the small tables in full, the photos of 2021-12-03, and the first
300 lines of each log file.

```sh
uv run photo-data          # generate (or show) the cached files
uv run photo-data --force  # regenerate (the files are the same each time)
uv run pytest              # checks: deterministic, keys and references, logs match the truth
```

```python
import photo_data as d

d.photos()  # one row per photo (pandas DataFrame)
d.access_logs()  # paths of the four nginx access logs
d.incidents()  # what really happened in the logs
```

## Tables (`data/tables/`)

| Table | Rows | Notes |
|---|---|---|
| `users` | 300 | `user_id`, `account_name`, `region` (us-east, us-west, eu-west, asia-east), `photos_total`, `last_login` |
| `cameras` | 20 | phones and cameras (`manufacturer`, `print_name`) |
| `photos` | 40,000 | `photo_id` (in upload order), `user_id`, storage `path`, `upload_date`, `size` (MB), `camera_id`, `camera_setting`, `format` (jpg, heic, png), `title`, true `objects` and `people` (user ids) |
| `albums`, `album_photos` | 313, 8,856 | albums of a user; `shared` albums have followers |
| `album_followers` | 756 | users who follow a shared album (many-to-many) |
| `friendships` | 1,610 | pairs of users |
| `devices` | 300 | phone, camera, app version, and whether the phone saves HEIC |

The users are not equal: `ckaestne` (user 54351) has 5,124 photos, most users have a few
dozen, and `eva.burk` (user 13221) has 3. Uploads come in short sessions, more on weekends
and holidays (Thanksgiving, Christmas), mostly in the afternoon and evening of the user's
time zone. The photos `133422131` to `133422133`, the two users, and the cameras 663 and
1844 have the values of the lecture examples.

## Logs (`data/logs/`)

| File | Format | Content |
|---|---|---|
| `web/access-web-{1..4}.log` | nginx combined log | about 49,000 requests to 4 web servers: photo views (`GET /st/...`), thumbnails, static files, API calls, uploads, logins, bots |
| `web/error-web-{1..4}.log` | nginx error log | failed upstream requests, large responses |
| `services/upload.jsonl` | JSON lines | the upload service |
| `services/thumbnailer.log` | Python logging | the thumbnail service |
| `ops/deploy.log` | logfmt | deployments and rollbacks |
| `ops/auth.log` | syslog | logins |
| `ops/cron.log` | syslog | nightly batch jobs |
| `mobile/crashes.jsonl` | JSON lines | crash reports of the Android and iOS apps |

Two incidents are in the logs (details and counts in `truth/incidents.json`):

1. On 2021-12-07 from 15:52 to 23:04 UTC, a new version of the thumbnail service cannot read
   HEIC images. Each HEIC upload fails (nginx returns 502), the iOS app retries and often
   crashes, and the photos arrive only after the rollback. `truth/failed_uploads.csv` lists
   each failed request.
2. On 2021-12-08 from 03:05 to 03:25 UTC, one address tries 190 logins with many account
   names, until the rate limit blocks it.

## How the data is made

`generate.py` makes the users, their friendships and devices, and then the upload sessions of
each user. It sorts all photos by upload time and numbers them, so that the photos of the
lecture examples get their IDs. `logs.py` simulates the requests of the three days: who is
active (users with more photos are more active), when (time zone), and what they request
(their own photos, photos of friends, popular photos of shared albums). Each log line of the
other services follows from a request, so that the logs are consistent with each other.
