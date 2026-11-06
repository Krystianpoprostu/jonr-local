"""Tiny .env helper: read/update KEY=VALUE pairs without ever printing values.

CLI usage (prompts with hidden input, never echoes the value):
    python tools/envfile.py set HA_TOKEN
    python tools/envfile.py set HA_URL --visible
    python tools/envfile.py show        # prints key names only
"""
from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load(path: Path = ENV_PATH) -> dict[str, str]:
    data: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip()
    return data


def update(values: dict[str, str], path: Path = ENV_PATH) -> None:
    data = load(path)
    data.update(values)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        for k, v in data.items():
            f.write(f"{k}={v}\n")
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set")
    s.add_argument("key")
    s.add_argument("--visible", action="store_true", help="echo input (for non-secret values)")
    sub.add_parser("show")
    a = p.parse_args()
    if a.cmd == "set":
        prompt = f"{a.key}: "
        value = input(prompt) if a.visible else getpass.getpass(prompt + "(hidden) ")
        value = value.strip()
        if not value:
            raise SystemExit("Empty value — nothing saved.")
        update({a.key: value})
        print(f"Saved {a.key} to {ENV_PATH} (mode 600).")
    else:
        for k in load():
            print(k)


if __name__ == "__main__":
    main()
