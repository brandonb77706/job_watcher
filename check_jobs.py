# check_jobs.py
import os
import json
import hashlib
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

STATE_FILE = "jobs_seen.json"


def load_seen_jobs():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_seen_jobs(seen):
    with open(STATE_FILE, "w") as f:
        json.dump(seen, f, indent=2)


def fetch_jobs(url: str, selector: str | None = None):
    """
    Returns a list of job dicts: {"id": str, "title": str, "link": str}
    """
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    jobs = []

    if selector:
        elements = soup.select(selector)
    else:
        # Fallback: any link containing 'job' in its href
        elements = soup.find_all("a", href=True)
        elements = [a for a in elements if "job" in a["href"].lower()]

    base = resp.url  # in case of redirects

    for el in elements:
        # Try to get title
        text = el.get_text(strip=True)
        if not text:
            continue

        # Try to get link
        link = el.get("href") or ""
        if link.startswith("#"):
            # skip purely anchor links
            continue
        link = urljoin(base, link)

        # Create a stable ID from title+link
        raw_id = f"{text}|{link}"
        job_id = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:16]

        jobs.append(
            {
                "id": job_id,
                "title": text,
                "link": link,
            }
        )

    return jobs


def send_webhook_notification(webhook_url: str, site_name: str, new_jobs: list[dict]):
    if not new_jobs:
        return

    lines = [f"📢 New job(s) detected on **{site_name}**:"]
    for job in new_jobs:
        lines.append(f"- [{job['title']}]({job['link']})")

    content = "\n".join(lines)

    payload = {"content": content}
    resp = requests.post(webhook_url, json=payload, timeout=15)
    resp.raise_for_status()


def main():
    job_url = os.environ.get("JOB_URL")
    if not job_url:
        raise RuntimeError("JOB_URL is not set")

    selector = os.environ.get("JOB_SELECTOR")  # optional
    site_name = os.environ.get("JOB_SITE_NAME", job_url)
    webhook_url = os.environ.get("WEBHOOK_URL")  # optional

    print(f"Checking jobs on: {job_url}")
    if selector:
        print(f"Using CSS selector: {selector}")

    current_jobs = fetch_jobs(job_url, selector)
    print(f"Found {len(current_jobs)} job elements")

    seen = load_seen_jobs()

    new_jobs = []
    for job in current_jobs:
        if job["id"] not in seen:
            new_jobs.append(job)
            seen[job["id"]] = {
                "title": job["title"],
                "link": job["link"],
            }

    if new_jobs:
        print(f"🚀 Found {len(new_jobs)} new job(s):")
        for job in new_jobs:
            print(f"- {job['title']} | {job['link']}")

        if webhook_url:
            try:
                send_webhook_notification(webhook_url, site_name, new_jobs)
                print("✅ Webhook notification sent")
            except Exception as e:
                print(f"⚠️ Failed to send webhook notification: {e}")
    else:
        print("No new jobs since last check.")

    save_seen_jobs(seen)
    print("State updated and saved.")


if __name__ == "__main__":
    main()