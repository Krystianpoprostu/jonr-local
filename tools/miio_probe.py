"""Minimal read-only miIO LAN client (no python-miio needed). Reads IP/token from .env, never prints the token.
Usage: python tools/miio_probe.py <method> [json-params]"""
import hashlib, json, re, socket, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import envfile
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

def call(ip, token_hex, method, params=None, timeout=5):
    token = bytes.fromhex(token_hex)
    key = hashlib.md5(token).digest(); iv = hashlib.md5(key + token).digest()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(timeout)
    s.sendto(bytes.fromhex("21310020" + "ff" * 28), (ip, 54321))
    hello, _ = s.recvfrom(1024)
    did, stamp = hello[8:12], int.from_bytes(hello[12:16], "big")
    payload = json.dumps({"id": int(time.time()) % 100000, "method": method, "params": params or []}).encode()
    enc = AES.new(key, AES.MODE_CBC, iv).encrypt(pad(payload, 16))
    header = b"\x21\x31" + (32 + len(enc)).to_bytes(2, "big") + b"\x00" * 4 + did + (stamp + 1).to_bytes(4, "big")
    checksum = hashlib.md5(header + token + enc).digest()
    s.sendto(header + checksum + enc, (ip, 54321))
    resp, _ = s.recvfrom(65535)
    dec = unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(resp[32:]), 16)
    return json.loads(dec.rstrip(b"\x00"))

_REDACT = {"token", "mac", "uid", "ssid", "bssid", "bssid_list", "localIp", "gw", "mask", "sn"}


def redact(obj):
    """Mask identifiers in a device answer (miIO.info carries the TOKEN itself)."""
    if isinstance(obj, dict):
        return {k: ("<redacted>" if k in _REDACT else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    if isinstance(obj, str) and re.fullmatch(r"[0-9a-fA-F]{32}", obj):
        return "<redacted-hex>"
    return obj


if __name__ == "__main__":
    env = envfile.load()
    params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else None
    answer = call(env["MIIO_IP"], env["MIIO_TOKEN"], sys.argv[1], params)
    print(json.dumps(redact(answer), indent=1, ensure_ascii=False))
