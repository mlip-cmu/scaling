import argparse

from . import ensure


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the synthetic photo service dataset.")
    parser.add_argument("--force", action="store_true", help="regenerate even if cached")
    path = ensure(force=parser.parse_args().force)
    for f in sorted(path.rglob("*")):
        if f.is_file() and "preview" not in f.parts and not f.name.startswith("VERSION"):
            print(f"{f.relative_to(path)}  {f.stat().st_size / 1e6:.2f} MB")
