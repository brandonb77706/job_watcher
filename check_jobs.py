import os
import json
import hashlib
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

STATE_FILE = "jobs_seen.json"


def load_seen_jobs():
    """Load previously seen jobs from a local JSON file."""
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        # If file is corrupted or unreadable, start fresh
        return {}


def save_seen_jobs(seen):
    """Save seen jobs to a local JSON file."""
    with open(STATE_FILE, "w") as f:
        json.dump(seen, f, indent=2)


def fetch_jobs(url, selector=None):
    """
    Fetch job listings from a page.

    Returns a list of dicts: {"id": str, "title": str, "link": str}
    """
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    if selector:
        elements = soup.select(selector)
    else:
        # Fallback: any link that looks job-ish
        elements = soup.find_all("a", href=True)
        elements = [a for a in elements if "job" in a["href"].lower()]

    jobs = []
    base = resp.url  # handle redirects

    for el in elements:
        text = el.get_text(strip=True)
        if not text:
            continue

        href = el.get("href") or ""
        if not href or href.startswith("#"):
            continue

        link = urljoin(base, href)

        # Create stable ID based on title+link
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


def send_webhook_notification(webhook_url, site_name, new_jobs):
    """Optional: send a Discord-style webhook notification."""
    if not webhook_url or not new_jobs:
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

    has_new = False
    email_body = ""

    if new_jobs:
        has_new = True
        print(f"🚀 Found {len(new_jobs)} new job(s):")

        # Build HTML body for email
        lines = [f"<h2>New job(s) on {site_name}</h2>", "<ul>"]
        for job in new_jobs:
            print(f"- {job['title']} | {job['link']}")
            lines.append(f"<li><a href='{job['link']}'>{job['title']}</a></li>")
        lines.append("</ul>")
        email_body = "\n".join(lines)

        # Optional: Discord / webhook
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

    # 🔥 Expose outputs for GitHub Actions
    # (used by the email step in job-check.yml)
    print(f"::set-output name=has_new::{str(has_new).lower()}")
    print(f"::set-output name=email_body::{email_body}")


if __name__ == "__main__":
    main()