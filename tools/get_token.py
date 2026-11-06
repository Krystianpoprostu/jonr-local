"""Fetch the JONR P20 Pro MIoT token from the Mi cloud and store it in .env.

Wraps PiotrMachowski/Xiaomi-cloud-tokens-extractor (MIT), reusing its login
(QR code scanned with the Mi Home app, or password + 2FA/captcha). Unlike the
original script it NEVER prints tokens: only name/model/IP/region of devices.
Only the vacuum's token is persisted (.env next to this repo, mode 600).

    git clone https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor ../third_party/Xiaomi-cloud-tokens-extractor
    python tools/get_token.py

Set TOKEN_EXTRACTOR=/path/to/token_extractor.py to use another location.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import envfile  # noqa: E402

DEFAULT_EXTRACTOR = HERE.parent.parent / "third_party" / "Xiaomi-cloud-tokens-extractor" / "token_extractor.py"
EXTRACTOR = Path(os.environ.get("TOKEN_EXTRACTOR", DEFAULT_EXTRACTOR))
TARGET_MODEL = "xtl.vacuum.xm2216"


def load_extractor():
    """Import token_extractor.py (it parses sys.argv at import: give it a clean,
    interactive argv — no password on the command line, log level CRITICAL)."""
    if not EXTRACTOR.exists():
        raise SystemExit(f"token_extractor.py not found at {EXTRACTOR} (see the docstring)")
    sys.argv = [str(EXTRACTOR)]
    spec = importlib.util.spec_from_file_location("token_extractor", EXTRACTOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    te = load_extractor()
    print("Xiaomi account login.")
    print("  q = QR code (recommended: scan it with the Mi Home app, no password typed)")
    print("  p = e-mail/phone + password (+ 2FA code from e-mail if asked)")
    method = ""
    while method not in ("p", "q"):
        method = input("p/q: ").strip().lower()
    conn = te.QrCodeXiaomiCloudConnector() if method == "q" else te.PasswordXiaomiCloudConnector()
    if not conn.login():
        raise SystemExit("Login failed.")
    print("Logged in. Searching regions:", ", ".join(te.SERVERS))

    found: list[tuple[str, dict]] = []
    for server in te.SERVERS:
        homes = []
        try:
            h = conn.get_homes(server)
            if h:
                homes += [(x["id"], conn.userId) for x in h["result"]["homelist"]]
            c = conn.get_dev_cnt(server)
            if c:
                homes += [(x["home_id"], x["home_owner"]) for x in c["result"]["share"]["share_family"]]
        except Exception as e:  # noqa: BLE001
            print(f"  [{server}] query failed: {type(e).__name__}")
            continue
        for home_id, owner in homes:
            d = conn.get_devices(server, home_id, owner)
            for dev in (d or {}).get("result", {}).get("device_info") or []:
                print(f"  [{server}] {dev.get('name')!s:30} {dev.get('model')!s:28} IP {dev.get('localip')}")
                if dev.get("model") == TARGET_MODEL:
                    found.append((server, dev))

    if not found:
        raise SystemExit(f"No {TARGET_MODEL} found on this account.")
    if len(found) > 1:
        print(f"Note: {len(found)} {TARGET_MODEL} devices; using the first one.")
    server, dev = found[0]
    token = dev.get("token", "")
    if len(token) != 32:
        raise SystemExit("Unexpected token format — nothing saved.")
    envfile.update({
        "MIIO_IP": dev.get("localip", ""),
        "MIIO_TOKEN": token,
        "MIIO_DID": str(dev.get("did", "")),
        "MIIO_MODEL": TARGET_MODEL,
        "XIAOMI_SERVER": server,
    })
    print()
    print(f"OK: {dev.get('name')} | region {server} | IP {dev.get('localip')} | did {dev.get('did')}")
    print(f"Token (32 chars) saved to {envfile.ENV_PATH} — not displayed.")


if __name__ == "__main__":
    main()
