"""Fixed vocabularies: names, cameras, objects, and the rows that appear on the slides."""

FIRST = [
    "anna", "ben", "carla", "david", "elena", "felix", "grace", "hiro", "ines", "jamal",
    "kim", "luca", "maya", "noah", "olga", "priya", "quinn", "rosa", "sam", "tara",
    "umar", "vera", "wei", "ximena", "yusuf", "zoe", "amir", "bianca", "chen", "dana",
    "emil", "fatima", "gabe", "hana", "ivan", "julia", "kofi", "lena", "marco", "nadia",
]  # fmt: skip
LAST = [
    "adams", "baker", "costa", "dubois", "evans", "fischer", "garcia", "huang", "ito",
    "jensen", "kowalski", "lopez", "meyer", "nakamura", "okafor", "patel", "quist", "rossi",
    "silva", "tanaka", "ueda", "vogel", "wang", "xu", "yilmaz", "zimmer", "burk", "novak",
]  # fmt: skip

# Regions of the users and the offset of their local time to UTC (hours).
REGIONS = {"us-east": -5, "us-west": -8, "eu-west": 0, "asia-east": 8}
REGION_SHARE = [0.45, 0.25, 0.2, 0.1]

# camera_id, manufacturer, print_name, kind, aperture, focal length (mm), share of users
CAMERAS = [
    (663, "Google", "Google Pixel 5", "android", 1.8, 4.44, 0.07),
    (671, "Google", "Google Pixel 6", "android", 1.85, 6.81, 0.06),
    (1844, "Motorola", "Motorola MotoG3", "android", 2.0, 3.64, 0.02),
    (1901, "Motorola", "Motorola Edge 20", "android", 1.9, 5.4, 0.02),
    (2210, "Samsung", "Samsung Galaxy S21", "android", 1.8, 5.4, 0.1),
    (2214, "Samsung", "Samsung Galaxy A52", "android", 1.8, 5.2, 0.08),
    (2231, "Samsung", "Samsung Galaxy S20", "android", 1.8, 5.4, 0.05),
    (3302, "OnePlus", "OnePlus 9", "android", 1.8, 5.6, 0.03),
    (3515, "Xiaomi", "Xiaomi Mi 11", "android", 1.85, 6.0, 0.03),
    (4101, "Apple", "Apple iPhone 11", "ios", 1.8, 4.25, 0.1),
    (4102, "Apple", "Apple iPhone 12", "ios", 1.6, 4.2, 0.13),
    (4103, "Apple", "Apple iPhone 12 Pro", "ios", 1.6, 4.2, 0.06),
    (4104, "Apple", "Apple iPhone 13", "ios", 1.6, 5.1, 0.1),
    (4105, "Apple", "Apple iPhone SE", "ios", 1.8, 3.99, 0.05),
    (5020, "Canon", "Canon EOS R6", "camera", 4.0, 50.0, 0.0),
    (5031, "Canon", "Canon EOS 90D", "camera", 5.6, 35.0, 0.0),
    (6110, "Sony", "Sony ILCE-7M3", "camera", 2.8, 35.0, 0.0),
    (6124, "Sony", "Sony DSC-RX100M7", "camera", 2.8, 9.0, 0.0),
    (7002, "Nikon", "Nikon Z 6II", "camera", 4.0, 70.0, 0.0),
    (8015, "Fujifilm", "Fujifilm X-T4", "camera", 2.0, 23.0, 0.0),
]
PRO_CAMERAS = [c[0] for c in CAMERAS if c[3] == "camera"]

APP_VERSION = {"android": "5.2.0", "ios": "7.4.1"}
OS_VERSION = {"android": ["Android 11", "Android 12"], "ios": ["iOS 15.1", "iOS 14.8"]}

# Objects in photos (the true labels behind the keyword search) and the months in which they
# are more common.
OBJECTS = {
    "person": 6.0, "sky": 3.0, "tree": 3.0, "building": 2.0, "food": 2.0, "dog": 1.5,
    "cat": 1.2, "car": 1.0, "flower": 1.5, "bird": 0.8, "beach": 1.0, "mountain": 1.0,
    "lake": 0.8, "bicycle": 0.5, "cake": 0.6, "sunset": 1.0, "snow": 0.4, "pumpkin": 0.1,
    "christmas tree": 0.1, "fireworks": 0.1, "leaves": 0.5,
}  # fmt: skip
SEASON = {
    "beach": {7: 4, 8: 4, 9: 1.5},
    "flower": {7: 2, 8: 1.5},
    "leaves": {10: 5, 11: 3},
    "pumpkin": {10: 20, 11: 3},
    "snow": {12: 8, 11: 2},
    "christmas tree": {12: 40},
    "fireworks": {7: 10},
}

TITLES = [
    "Sunset", "Birthday", "Hike", "Beach day", "Family", "Road trip", "Dinner", "Snow day",
    "Wedding", "Graduation", "Pittsburgh", "Garden", "First day of school", "Halloween",
    "Thanksgiving", "Christmas", "Game night", "Concert",
]  # fmt: skip
ALBUM_TITLES = [
    "Summer 2021", "Family", "Vacation", "Friends", "Hiking", "Food", "Pets", "Wedding",
    "Road trip", "Fall colors", "Holidays", "Garden", "Concerts", "Kids", "Best of 2021",
]  # fmt: skip

# The rows that the lecture slides show (tables "Photos", "Users", "Cameras").
SLIDE_USERS = [
    # user_id, account_name, region, photos_total, last_login
    (54351, "ckaestne", "us-east", 5124, "2021-12-08T12:27:48.497Z"),
    (13221, "eva.burk", "eu-west", 3, "2021-12-21T01:51:54.713Z"),
]
SLIDE_PHOTOS = [
    # photo_id, user_id, path, upload_date, size (MB), camera_id, camera_setting
    (133422131, 54351, "/st/u211/1U6uFl47Fy.jpg", "2021-12-03T09:18:32.124Z", 5.7, 663,
     "ƒ/1.8; 1/120; 4.44mm; ISO271"),
    (133422132, 13221, "/st/u11b/MFxlL1FY8V.jpg", "2021-12-03T09:18:32.129Z", 3.1, 1844,
     "ƒ/2, 1/15, 3.64mm, ISO1250"),
    (133422133, 54351, "/st/x81/ITzhcSmv9s.jpg", "2021-12-03T09:18:32.131Z", 4.8, 663,
     "ƒ/1.8; 1/120; 4.44mm; ISO48"),
]  # fmt: skip
