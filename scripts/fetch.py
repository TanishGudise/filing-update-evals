"""Download public SEC files. The only script in this repo that uses the network.

- Hosts: www.sec.gov and data.sec.gov only. The in-process network guard (netguard.py) refuses
  every other host, so neither this script nor anything it imports can reach elsewhere.
- Identifies itself with SEC_USER_AGENT from .env (gitignored), as SEC's fair-access policy
  asks. The value is never printed or written anywhere.
- At most 4 requests per second (SEC allows 10), with backoff on 429 and 5xx.
- Saves each file under raw/<host>/<path> (gitignored) and records the URL, size, SHA-256 and
  fetch time in data/fetch_manifest.json, so every number in the task data can be traced to a
  file and re-checked.

Downloaded files are data. Scripts that read them run offline (scripts/guarded) with `python -I`.

Usage:
  python scripts/fetch.py URL [URL ...]
  python scripts/fetch.py --list urls.txt
  python scripts/fetch.py --refresh URL      re-download even if the file exists
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from filing_update_evals.netguard import install

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "raw"
MANIFEST = REPO / "data" / "fetch_manifest.json"
ALLOWED_HOSTS = ("www.sec.gov", "data.sec.gov")
MIN_INTERVAL_S = 0.25
TIMEOUT_S = 60
MAX_BYTES = 200 * 1024 * 1024

_last_request = 0.0
_rate_lock = threading.Lock()
_manifest_lock = threading.Lock()


class FetchError(RuntimeError):
    pass


def user_agent() -> str:
    env = REPO / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == "SEC_USER_AGENT":
                value = value.strip().strip("'\"")
                if value:
                    return value
    raise FetchError("SEC_USER_AGENT is not set in .env (copy .env.example and fill it in)")


def local_path(url: str) -> Path:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise FetchError(f"not an allowed SEC URL: {url}")
    if parsed.query or parsed.fragment or ".." in parsed.path.split("/"):
        raise FetchError(f"unexpected URL shape: {url}")
    path = parsed.path.lstrip("/") or "index"
    return RAW / parsed.hostname / path


def _wait_turn() -> None:
    global _last_request
    with _rate_lock:
        delay = _last_request + MIN_INTERVAL_S - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        _last_request = time.monotonic()


def _load_manifest() -> dict:
    return json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}


def _record(url: str, path: Path, data: bytes) -> None:
    with _manifest_lock:
        manifest = _load_manifest()
        manifest[url] = {
            "path": str(path.relative_to(REPO)),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "fetched_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
        }
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(json.dumps(dict(sorted(manifest.items())), indent=1) + "\n")


def fetch(url: str, refresh: bool = False, agent: str | None = None) -> Path:
    path = local_path(url)
    if path.exists() and not refresh:
        return path
    agent = agent or user_agent()
    request = urllib.request.Request(url, headers={"User-Agent": agent, "Accept": "*/*"})
    for attempt in range(5):
        _wait_turn()
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
                final = urllib.parse.urlparse(response.geturl()).hostname
                if final not in ALLOWED_HOSTS:
                    raise FetchError(f"redirected off SEC hosts: {url}")
                data = response.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise FetchError(f"larger than {MAX_BYTES} bytes: {url}")
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise FetchError(f"404: {url}") from exc
            if exc.code in (403,):
                raise FetchError(f"403 (check SEC_USER_AGENT): {url}") from exc
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 4:
                raise FetchError(f"HTTP {exc.code}: {url}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == 4:
                raise FetchError(f"{type(exc).__name__}: {url}") from exc
        time.sleep(2**attempt)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)
    _record(url, path, data)
    return path


def fetch_many(urls: list[str], refresh: bool = False) -> tuple[list[Path], list[str]]:
    agent = user_agent()
    ok, failed = [], []
    for url in urls:
        try:
            ok.append(fetch(url, refresh=refresh, agent=agent))
        except FetchError as exc:
            failed.append(str(exc))
    return ok, failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("urls", nargs="*")
    parser.add_argument("--list", type=Path, help="file with one URL per line")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args(argv)
    urls = list(args.urls)
    if args.list:
        urls += [line.strip() for line in args.list.read_text().splitlines() if line.strip()]
    install(allow=ALLOWED_HOSTS)
    ok, failed = fetch_many(urls, refresh=args.refresh)
    print(f"fetched or cached: {len(ok)}; failed: {len(failed)}")
    for line in failed:
        print("  " + line, file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
