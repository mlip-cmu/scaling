-- The photo service as normalized tables: each fact is stored once, and tables refer to each
-- other by keys.
CREATE TABLE users (
    user_id      BIGINT PRIMARY KEY,
    account_name TEXT NOT NULL UNIQUE,
    region       TEXT NOT NULL,
    photos_total INTEGER NOT NULL,
    last_login   TIMESTAMPTZ
);

CREATE TABLE cameras (
    camera_id    INTEGER PRIMARY KEY,
    manufacturer TEXT NOT NULL,
    print_name   TEXT NOT NULL
);

CREATE TABLE photos (
    photo_id       BIGINT PRIMARY KEY,
    user_id        BIGINT NOT NULL REFERENCES users,
    path           TEXT NOT NULL UNIQUE,
    upload_date    TIMESTAMPTZ NOT NULL,
    size           REAL NOT NULL,
    camera_id      INTEGER REFERENCES cameras,
    camera_setting TEXT,
    title          TEXT
);
CREATE INDEX photos_user ON photos (user_id);

CREATE TABLE albums (
    album_id INTEGER PRIMARY KEY,
    owner_id BIGINT NOT NULL REFERENCES users,
    title    TEXT NOT NULL,
    shared   BOOLEAN NOT NULL
);

-- many-to-many relations: a table of pairs
CREATE TABLE album_photos (
    album_id INTEGER REFERENCES albums,
    photo_id BIGINT REFERENCES photos,
    PRIMARY KEY (album_id, photo_id)
);

CREATE TABLE album_followers (
    album_id INTEGER REFERENCES albums,
    user_id  BIGINT REFERENCES users,
    PRIMARY KEY (album_id, user_id)
);
