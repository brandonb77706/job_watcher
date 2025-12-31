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


def is_internship(job_title):
    """Check if a job title indicates it's an internship."""
    title_lower = job_title.lower()
    internship_keywords = [
        'intern', 'internship', 'summer', 'co-op', 'co op', 'coop',
        'student', 'entry level', 'new grad', 'recent grad', 'graduate program'
    ]
    return any(keyword in title_lower for keyword in internship_keywords)


def fetch_jobs(url, selector=None):
    """
    Fetch job listings from a page.

    Returns a list of dicts: {"id": str, "title": str, "link": str}
    """
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ Failed to fetch {url}: {e}")
        return []

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

        # Filter for internships only
        if not is_internship(text):
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


def send_webhook_notification(webhook_url, all_new_jobs_by_site):
    """Optional: send a Discord-style webhook notification."""
    if not webhook_url or not any(all_new_jobs_by_site.values()):
        return

    lines = ["📢 New internship(s) detected:"]
    
    for site_name, new_jobs in all_new_jobs_by_site.items():
        if new_jobs:
            lines.append(f"\n**{site_name}**:")
            for job in new_jobs:
                lines.append(f"- [{job['title']}]({job['link']})")

    content = "\n".join(lines)
    payload = {"content": content}

    resp = requests.post(webhook_url, json=payload, timeout=15)
    resp.raise_for_status()


def create_email_body(all_new_jobs_by_site):
    """Create a nicely formatted HTML email body for multiple sites."""
    # Count total jobs
    total_jobs = sum(len(jobs) for jobs in all_new_jobs_by_site.values())
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
                background-color: #f8f9fa;
            }}
            .container {{
                background-color: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            .header {{
                text-align: center;
                margin-bottom: 30px;
                padding-bottom: 20px;
                border-bottom: 2px solid #007acc;
            }}
            .header h1 {{
                color: #007acc;
                margin: 0;
                font-size: 28px;
                font-weight: 600;
            }}
            .subtitle {{
                color: #666;
                margin-top: 10px;
                font-size: 16px;
            }}
            .site-section {{
                margin-bottom: 30px;
            }}
            .site-title {{
                font-size: 20px;
                font-weight: 600;
                color: #2c3e50;
                margin-bottom: 15px;
                padding-bottom: 8px;
                border-bottom: 1px solid #ddd;
            }}
            .job-card {{
                background-color: #f8fffe;
                border: 1px solid #e3f2fd;
                border-radius: 8px;
                padding: 20px;
                margin-bottom: 15px;
                transition: transform 0.2s;
            }}
            .job-card:hover {{
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            }}
            .job-title {{
                font-size: 16px;
                font-weight: 600;
                color: #2c3e50;
                margin-bottom: 10px;
                line-height: 1.4;
            }}
            .job-link {{
                display: inline-block;
                background-color: #007acc;
                color: white !important;
                padding: 8px 16px;
                text-decoration: none;
                border-radius: 5px;
                font-weight: 500;
                font-size: 14px;
                transition: background-color 0.3s;
            }}
            .job-link:hover {{
                background-color: #005999;
            }}
            .footer {{
                text-align: center;
                margin-top: 30px;
                padding-top: 20px;
                border-top: 1px solid #eee;
                color: #666;
                font-size: 14px;
            }}
            .job-count {{
                background-color: #e8f5e8;
                color: #2e7d32;
                padding: 8px 16px;
                border-radius: 20px;
                font-weight: 600;
                display: inline-block;
                margin-bottom: 20px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎉 New Internship Opportunities!</h1>
                <div class="subtitle">Fresh opportunities from multiple job sites</div>
            </div>
            
            <div class="job-count">
                {total_jobs} new internship{'s' if total_jobs != 1 else ''} found across {len([s for s, jobs in all_new_jobs_by_site.items() if jobs])} site{'s' if len([s for s, jobs in all_new_jobs_by_site.items() if jobs]) != 1 else ''}
            </div>
    """
    
    for site_name, new_jobs in all_new_jobs_by_site.items():
        if new_jobs:
            html += f"""
            <div class="site-section">
                <div class="site-title">{site_name}</div>
            """
            
            for job in new_jobs:
                html += f"""
                <div class="job-card">
                    <div class="job-title">{job['title']}</div>
                    <a href="{job['link']}" class="job-link" target="_blank">View Application →</a>
                </div>
                """
            
            html += "</div>"
    
    html += """
            <div class="footer">
                <p>Good luck with your applications! 🚀</p>
                <p><small>This is an automated notification from your Job Watcher</small></p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html


def load_job_sites_config():
    """Load job sites configuration from environment variables or default config."""
    # Try to load from JOB_SITES_CONFIG environment variable (JSON string)
    config_json = os.environ.get("JOB_SITES_CONFIG")
    if config_json:
        try:
            return json.loads(config_json)
        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse JOB_SITES_CONFIG: {e}")
            print("Falling back to single site configuration...")
    
    # Fallback to single site configuration (backward compatibility)
    job_url = os.environ.get("JOB_URL")
    if job_url:
        selector = os.environ.get("JOB_SELECTOR")
        site_name = os.environ.get("JOB_SITE_NAME", job_url)
        
        return [
            {
                "name": site_name,
                "url": job_url,
                "selector": selector
            }
        ]
    
    # If no configuration found, raise error
    raise RuntimeError("No job sites configuration found. Please set JOB_SITES_CONFIG or JOB_URL environment variable.")


def main():
    # Load configuration for multiple job sites
    job_sites = load_job_sites_config()
    
    print(f"Checking internships on {len(job_sites)} job site(s):")
    for site in job_sites:
        print(f"  - {site['name']}: {site['url']}")

    seen = load_seen_jobs()
    all_new_jobs_by_site = {}
    total_jobs_found = 0

    # Check each job site
    for site_config in job_sites:
        site_name = site_config["name"]
        url = site_config["url"]
        selector = site_config.get("selector")
        
        print(f"\n🔍 Checking {site_name}...")
        if selector:
            print(f"   Using CSS selector: {selector}")

        current_jobs = fetch_jobs(url, selector)
        total_jobs_found += len(current_jobs)
        print(f"   Found {len(current_jobs)} internship opportunities")

        new_jobs = []
        for job in current_jobs:
            # Add site name to job ID to avoid conflicts between sites
            site_job_id = f"{site_name}::{job['id']}"
            if site_job_id not in seen:
                new_jobs.append(job)
                seen[site_job_id] = {
                    "title": job["title"],
                    "link": job["link"],
                    "site": site_name
                }

        if new_jobs:
            print(f"   🚀 Found {len(new_jobs)} new internship(s)")
            for job in new_jobs:
                print(f"     - {job['title']} | {job['link']}")
        else:
            print(f"   No new internships since last check")
            
        all_new_jobs_by_site[site_name] = new_jobs

    # Summary
    total_new_jobs = sum(len(jobs) for jobs in all_new_jobs_by_site.values())
    has_new = total_new_jobs > 0

    print(f"\n📊 Summary:")
    print(f"   Total jobs found: {total_jobs_found}")
    print(f"   New jobs: {total_new_jobs}")

    email_body = ""
    if has_new:
        # Build HTML body for email
        email_body = create_email_body(all_new_jobs_by_site)

        # Optional: Discord / webhook
        webhook_url = os.environ.get("WEBHOOK_URL")
        if webhook_url:
            try:
                send_webhook_notification(webhook_url, all_new_jobs_by_site)
                print("✅ Webhook notification sent")
            except Exception as e:
                print(f"⚠️ Failed to send webhook notification: {e}")

    save_seen_jobs(seen)
    print("State updated and saved.")

    # 🔥 Expose outputs for GitHub Actions using Environment Files
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"has_new={str(has_new).lower()}\n")
            # Use multiline format for email_body to handle special characters
            f.write("email_body<<EOF\n")
            f.write(f"{email_body}\n")
            f.write("EOF\n")
    else:
        # Fallback for local testing
        print(f"has_new={str(has_new).lower()}")


if __name__ == "__main__":
    main()