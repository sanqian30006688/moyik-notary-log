#!/usr/bin/env python3
"""Mirror Moyik's public notary log into this folder and check it while doing so.

Needs only Python 3.9+. Run it from anywhere:

    python3 mirror.py                # copy from https://moyik.com into the folder of this script
    python3 mirror.py --check-only   # re-check the files already here, without the network

What is copied is public by design: checkpoint numbers, fingerprints, Moyik's signatures and
the Bitcoin timestamp proofs. It holds nothing about any space or person.

The script never rewrites a checkpoint it has already saved. If the source ever serves a
different checkpoint under a number saved earlier, it stops with exit code 2 and says which
number: that is exactly the situation a mirror exists to expose.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

VERSION = "moyik-notary-v1"
FIXED = ("number", "prev_hash", "entry_count", "total_count", "root", "at_micros", "beacon", "checkpoint_hash")
LATE = ("key_id", "signature")  # a checkpoint may be signed a little after it is sealed
ZERO = "0" * 64
AGENT = "moyik-notary-mirror/1"


class Changed(Exception):
    """The source disagrees with what was saved earlier, or with itself."""


def preimage(c: dict) -> str:
    fields = [VERSION, "checkpoint", str(c["number"]), c["prev_hash"], str(c["entry_count"]),
              str(c["total_count"]), c["root"], str(c["at_micros"]), c.get("beacon") or ""]
    return "".join(f"{f}\n" for f in fields)


def signed_message(checkpoint_hash: str) -> bytes:
    return f"{VERSION}\nsigned-checkpoint\n{checkpoint_hash}\n".encode()


def get(url: str) -> bytes | None:
    request = urllib.request.Request(url, headers={"User-Agent": AGENT, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def write(path: Path, data: bytes) -> bool:
    if path.exists() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


def dump(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def checkpoint_path(root: Path, number: int) -> Path:
    return root / "checkpoints" / f"{number:08d}.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def check_one(c: dict) -> None:
    got = hashlib.sha256(preimage(c).encode()).hexdigest()
    if got != c["checkpoint_hash"]:
        raise Changed(f"checkpoint {c['number']}: its fingerprint does not match its own fields")


def verify_signature(c: dict, keys: dict) -> str:
    """'ok', 'unsigned', 'no-library' or raises Changed."""
    if not c.get("signature") or not c.get("key_id"):
        return "unsigned"
    key = keys.get(c["key_id"])
    if key is None:
        raise Changed(f"checkpoint {c['number']}: signed with key {c['key_id']}, which is not in keys.json")
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        return "no-library"
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(key["public_key"])).verify(
            bytes.fromhex(c["signature"]), signed_message(c["checkpoint_hash"]))
    except InvalidSignature:
        raise Changed(f"checkpoint {c['number']}: signature does not verify with key {c['key_id']}") from None
    return "ok"


def save_keys(root: Path, served: list) -> bool:
    path = root / "keys.json"
    saved = {k["key_id"]: k for k in (load(path) or [])}
    for k in served:
        old = saved.get(k["key_id"])
        if old and (old["public_key"] != k["public_key"] or old.get("alg") != k.get("alg")):
            raise Changed(f"key {k['key_id']}: the public key served now differs from the one saved earlier")
        saved[k["key_id"]] = {**(old or {}), **k}
    missing = set(saved) - {k["key_id"] for k in served}
    if missing and served:
        raise Changed(f"keys saved earlier are no longer served: {', '.join(sorted(missing))}")
    return write(path, dump(sorted(saved.values(), key=lambda k: k["key_id"])))


def save_checkpoint(root: Path, c: dict) -> bool:
    number = int(c["number"])
    check_one(c)
    record = {f: c.get(f) for f in FIXED + LATE}
    path = checkpoint_path(root, number)
    old = load(path)
    if old is not None:
        for f in FIXED:
            if str(old.get(f)) != str(record.get(f)):
                raise Changed(f"checkpoint {number}: field {f} differs from the copy saved earlier. HISTORY WAS REWRITTEN at the source, or this mirror was edited.")
        for f in LATE:
            if old.get(f) and old.get(f) != record.get(f):
                raise Changed(f"checkpoint {number}: {f} differs from the copy saved earlier")
    return write(path, dump(record))


def mirror(root: Path, base: str) -> int:
    changed = 0
    before = None
    newest = None
    anchored: list[tuple[int, list]] = []
    while True:
        url = f"{base}/.well-known/moyik-notary.json" + (f"?before={before}" if before else "")
        body = get(url)
        if body is None:
            raise SystemExit(f"{url} answered 404")
        page = json.loads(body)
        if before is None:
            changed += save_keys(root, page.get("keys", []))
        rows = page.get("checkpoints", [])
        if not rows:
            break
        all_known = True
        for c in rows:
            number = int(c["number"])
            newest = max(newest or 0, number)
            if not checkpoint_path(root, number).exists():
                all_known = False
            changed += save_checkpoint(root, c)
            if c.get("anchors"):
                anchored.append((number, c["anchors"]))
        before = min(int(c["number"]) for c in rows)
        if before <= 1 or all_known:
            break
    for number, anchors in anchored:
        anchors_path = root / "anchors" / f"{number:08d}.json"
        proof_path = root / "anchors" / f"moyik-checkpoint-{number}.txt.ots"
        settled = (load(anchors_path) or []) == anchors and proof_path.exists() and all(a.get("status") == "confirmed" for a in anchors)
        if settled:
            continue
        changed += write(anchors_path, dump(anchors))
        proof = get(f"{base}/.well-known/moyik-notary/checkpoint/{number}?file=ots")
        if proof:
            # A proof only ever grows (calendar promise, then the Bitcoin block), so the newest one replaces the older.
            changed += write(proof_path, proof)
            changed += write(root / "anchors" / f"moyik-checkpoint-{number}.txt", preimage(load(checkpoint_path(root, number))).encode())
    print(f"mirrored up to checkpoint {newest}; {changed} file(s) written")
    return changed


def check(root: Path) -> None:
    keys = {k["key_id"]: k for k in (load(root / "keys.json") or [])}
    files = sorted((root / "checkpoints").glob("*.json"))
    previous = None
    signed = unsigned = unchecked = 0
    for path in files:
        c = json.loads(path.read_text(encoding="utf-8"))
        number = int(c["number"])
        if path.name != f"{number:08d}.json":
            raise Changed(f"{path.name} holds checkpoint {number}")
        check_one(c)
        if previous is None:
            if number == 1 and c["prev_hash"] != ZERO:
                raise Changed("checkpoint 1 does not start the chain")
        else:
            if number != int(previous["number"]) + 1:
                raise Changed(f"checkpoints {previous['number']} and {number}: numbers in between are missing")
            if c["prev_hash"] != previous["checkpoint_hash"]:
                raise Changed(f"checkpoint {number} does not follow checkpoint {previous['number']}")
            if int(c["total_count"]) != int(previous["total_count"]) + int(c["entry_count"]):
                raise Changed(f"checkpoint {number}: the running total does not add up")
        result = verify_signature(c, keys)
        signed += result == "ok"
        unsigned += result == "unsigned"
        unchecked += result == "no-library"
        previous = c
    for proof in sorted((root / "anchors").glob("*.txt")):
        number = int(proof.stem.rsplit("-", 1)[1])
        c = load(checkpoint_path(root, number))
        if c is None or hashlib.sha256(proof.read_bytes()).hexdigest() != c["checkpoint_hash"]:
            raise Changed(f"{proof.name} is not the text of checkpoint {number}")
    note = f"{signed} signature(s) verified, {unsigned} not signed yet"
    if unchecked:
        note += f", {unchecked} not checked (install the 'cryptography' package to check signatures)"
    print(f"chain of {len(files)} checkpoint(s) is consistent; {note}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base", default="https://moyik.com", help="where the log is served")
    parser.add_argument("--dir", default=str(Path(__file__).resolve().parent), help="folder holding the mirror")
    parser.add_argument("--check-only", action="store_true", help="check the saved files, fetch nothing")
    args = parser.parse_args()
    root = Path(args.dir)
    try:
        if not args.check_only:
            mirror(root, args.base.rstrip("/"))
        check(root)
    except Changed as problem:
        print(f"PROBLEM: {problem}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
