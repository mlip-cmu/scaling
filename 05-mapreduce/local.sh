#!/usr/bin/env bash
# The same analysis on one machine: first with shell tools, then with the mapper and reducer.
set -eu
cd "$(dirname "$0")"
LOGS=(../photo-data/data/logs/web/access-*.log)

echo "1. The 5 most requested paths in ${#LOGS[@]} log files ($(cat "${LOGS[@]}" | wc -l) lines):"
cat "${LOGS[@]}" |
    awk '{print $7}' |
    sort |
    uniq -c |
    sort -r -n |
    head -n 5

echo
echo "2. The 5 most viewed photos: map | sort (the shuffle) | reduce:"
cat "${LOGS[@]}" | python3 mapper.py | sort | python3 reducer.py | sort -t$'\t' -k2,2nr -k1,1 |
    head -n 5 | tee out/top_photos_local.tsv
