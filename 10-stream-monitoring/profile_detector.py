"""Profile the object detector on one machine: where does the time go?

The monitoring shows that one instance is slow in the span "preprocess". A profiler shows
which function inside it takes the time.
"""

from pyinstrument import Profiler

import photo_data
from components import _truth, detect_objects

photos = photo_data.photos()
sample = photos[(photos.upload_date >= "2021-12-06") & (photos.format != "png")].head(10)
truth = _truth("objects")

for slow in (True, False):
    profiler = Profiler()
    profiler.start()
    for p in sample.to_dict("records"):
        detect_objects(p, truth, slow=slow)
    profiler.stop()
    print(f"=== {'object-detector-slow' if slow else 'object-detector'}: 10 photos ===")
    text = profiler.output_text(unicode=True, color=False)
    tree = text[text.index("Profile at") :].splitlines()[2:]
    print("\n".join(line for line in tree if line.strip()))
    print()
