#!/usr/bin/env bash
# Run the demos of all projects (or only the folders given as arguments), as the CI does.
# Projects with a compose.yaml start their servers with Docker and stop them afterwards.
set -euo pipefail
cd "$(dirname "$0")"
export DO_NOT_TRACK=1 MPLBACKEND=Agg

notebook() { uv run jupyter nbconvert --to notebook --execute --inplace "$1"; }

demo() {
  case "$1" in
    photo-data) uv run photo-data && uv run pytest -q ;;
    06-*) uv run check_system.py && uv run demo_scaling.py 1 3 6 8 && uv run demo_delivery.py \
            && uv run demo_ordering.py && uv run dataflow.py ;;
    *) echo "unknown project: $1" >&2; return 1 ;;
  esac
}

projects=("$@")
[ ${#projects[@]} -eq 0 ] && projects=(photo-data [0-9][0-9]-*/)
for p in "${projects[@]}"; do
  p=${p%/}
  echo "=== $p ==="
  (
    cd "$p" && mkdir -p out && uv sync --locked -q
    if [ -f compose.yaml ]; then
      trap 'docker compose down -v --remove-orphans >/dev/null 2>&1' EXIT
      docker compose up -d --build --wait --quiet-pull
    fi
    demo "$p"
  )
done
