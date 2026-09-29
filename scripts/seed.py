"""Create the demo user and ingest every PDF in sample-docs/ through the real API.

Usage:
    make seed                                   # inside the backend container
    API_BASE_URL=http://localhost:8000 python scripts/seed.py   # from the host

Idempotent: re-running skips the existing account and any PDF already uploaded
(matched by filename) that isn't in a failed state.
"""

import os
import sys
import time
from pathlib import Path

import httpx

API = os.environ.get("API_BASE_URL", "http://localhost:8000").rstrip("/") + "/api"
EMAIL = os.environ.get("DEMO_EMAIL", "demo@docmind.dev")
PASSWORD = os.environ.get("DEMO_PASSWORD", "Demo@12345")
ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = Path(os.environ.get("SAMPLE_DOCS_DIR", ROOT / "sample-docs"))
POLL_SECONDS = 1.0
TIMEOUT_SECONDS = 180


def login(client: httpx.Client) -> str:
    """Register the demo user if needed, then return an access token."""
    r = client.post(f"{API}/auth/register", json={"email": EMAIL, "password": PASSWORD})
    if r.status_code == 201:
        print(f"Created demo user {EMAIL}")
    elif r.status_code == 409:
        print(f"Demo user {EMAIL} already exists")
    else:
        sys.exit(f"Registration failed ({r.status_code}): {r.text}")
    r = client.post(f"{API}/auth/login", json={"email": EMAIL, "password": PASSWORD})
    if r.status_code != 200:
        sys.exit(f"Login failed ({r.status_code}): {r.text}")
    return r.json()["access_token"]


def main() -> None:
    pdfs = sorted(SAMPLE_DIR.glob("*.pdf"))
    if not pdfs:
        sys.exit(f"No PDFs found in {SAMPLE_DIR}")

    with httpx.Client(timeout=60) as client:
        token = login(client)
        client.headers["Authorization"] = f"Bearer {token}"

        existing = {d["filename"]: d for d in client.get(f"{API}/documents").raise_for_status().json()}
        to_upload = [p for p in pdfs if existing.get(p.name, {}).get("status") not in ("ready", "processing")]
        for p in pdfs:
            if p not in to_upload:
                print(f"  skip  {p.name} (already {existing[p.name]['status']})")

        if to_upload:
            files = [("files", (p.name, p.read_bytes(), "application/pdf")) for p in to_upload]
            r = client.post(f"{API}/documents", files=files)
            if r.status_code != 202:
                sys.exit(f"Upload failed ({r.status_code}): {r.text}")
            print(f"Uploaded {len(to_upload)} document(s); waiting for ingestion…")

        deadline = time.monotonic() + TIMEOUT_SECONDS
        while True:
            docs = client.get(f"{API}/documents").raise_for_status().json()
            mine = [d for d in docs if d["filename"] in {p.name for p in pdfs}]
            if all(d["status"] != "processing" for d in mine):
                break
            if time.monotonic() > deadline:
                sys.exit("Timed out waiting for ingestion")
            time.sleep(POLL_SECONDS)

    failed = False
    for d in sorted(mine, key=lambda d: d["filename"]):
        detail = d["error_message"] or f"{d['page_count']} pages, {d['chunk_count']} chunks"
        print(f"  {d['status']:<6} {d['filename']}  ({detail})")
        failed |= d["status"] != "ready"
    print(f"\nDone. Sign in as {EMAIL} / {PASSWORD}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
