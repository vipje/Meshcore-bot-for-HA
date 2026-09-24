#!/usr/bin/env python3
"""Runs every build-time patch in local_patches/ORDER, in that order, on the upstream source (cwd).

One Docker step for all patches instead of one per patch keeps the image far below Docker's layer limit. Each patch
still checks its own anchors; the first one that fails stops the build with its own message.
"""
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent


def order() -> list:
    names = []
    for line in (HERE / "ORDER").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            names.append(line)
    return names


def main() -> int:
    names = order()
    missing = [n for n in names if not (HERE / n).is_file()]
    unlisted = sorted(p.name for p in HERE.glob("patch_*.py") if p.name not in names)
    if missing or unlisted:
        print(f"PATCH ORDER WRONG - listed but missing: {missing}; present but not listed: {unlisted}")
        return 1
    for name in names:
        result = subprocess.run([sys.executable, str(HERE / name)])
        if result.returncode != 0:
            print(f"PATCH FAILED: {name}")
            return result.returncode
    print(f"{len(names)} patches applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
