import json
import os
import re
import time
from datetime import datetime
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# DeepSeek API client
client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com"
)


def get_all_company_profiles(url, region_name):
    """Get ALL company profile URLs by clicking 'Load More' until all are loaded"""
    print(f"🎮 Loading all {region_name} companies from gamecompanies.com...")
    print("   (This may take a few minutes)\n")

    # Setup Selenium
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")  # Run in background
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(
        options=options
    )  # Selenium Manager handles driver automatically

    try:
        driver.get(url)
        time.sleep(3)  # Let page load

        # Keep clicking "Load More" until it's gone
        click_count = 0
        while True:
            try:
                # Look for "Load More" button
                load_more = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located(
                        (
                            By.XPATH,
                            "//button[contains(text(), 'Load') or contains(text(), 'More') or contains(@class, 'load')]",
                        )
                    )
                )

                # Scroll to button and click it
                driver.execute_script("arguments[0].scrollIntoView();", load_more)
                time.sleep(1)
                load_more.click()
                click_count += 1
                print(f"   Clicked 'Load More' ({click_count} times)...")
                time.sleep(2)

            except:
                print(f"   ✓ All {region_name} companies loaded!\n")
                break

        # Get the full page source
        page_source = driver.page_source
        driver.quit()

        soup = BeautifulSoup(page_source, "lxml")

        # Find all company profile links
        all_a = soup.find_all("a", href=True)
        company_profiles = []
        seen_urls = set()

        for link in all_a:
            href = link.get("href", "")
            # Company profiles: /industries/{continent}/{region}-game-industry/{province}/{city}/{slug}
            # e.g. /industries/north-america/canadian-game-industry/british-columbia/burnaby/bitten-toast-games
            # Note: href contains "-game-industry/" not "/game-industry/"
            if "game-industry/" in href and href.count("/") >= 6:
                full_url = (
                    "https://gamecompanies.com" + href if href.startswith("/") else href
                )

                # Skip if we've already seen this URL
                if full_url in seen_urls:
                    continue

                # Get clean company name
                company_name = link.get_text(strip=True)

                # Clean up the name - remove everything after common patterns
                for pattern in [
                    "We ",
                    "A ",
                    "An ",
                    "The ",
                    "Studio",
                    "Developer",
                    "Publisher",
                ]:
                    if pattern in company_name and company_name.index(pattern) > 0:
                        company_name = company_name[
                            : company_name.index(pattern)
                        ].strip()
                        break

                # Use regex to get only the first capitalized word(s)
                match = re.match(
                    r"^([A-Z][a-zA-Z0-9\s&\-\.]+?)(?=[A-Z][a-z]+\s(?:is|are|make|create|develop|We|A |An |The |Studio|Publisher|Developer))",
                    company_name,
                )
                if match:
                    company_name = match.group(1).strip()

                # Fallback: if name is super long, take first few words
                if len(company_name) > 50:
                    words = company_name.split()
                    company_name = " ".join(words[:3])

                if company_name and full_url not in seen_urls:
                    company_profiles.append(
                        {
                            "name": company_name,
                            "profile_url": full_url,
                            "region": region_name,
                        }
                    )
                    seen_urls.add(full_url)

        print(f"   Found {len(company_profiles)} {region_name} company profiles\n")
        return company_profiles

    except Exception as e:
        driver.quit()
        print(f"   ❌ Error: {str(e)}")
        return []


def get_company_website(profile_url):
    """Extract company website from their profile page"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(profile_url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Find the "Website" label and get the link near it
        website = None

        # Look for text that says "Website"
        for element in soup.find_all(string=re.compile(r"Website", re.IGNORECASE)):
            parent = element.parent
            # Look for a link in the same parent or nearby siblings
            link = parent.find("a", href=True)
            if not link:
                link = parent.parent.find("a", href=True) if parent.parent else None
            if not link:
                next_elem = parent.find_next_sibling()
                if next_elem:
                    link = next_elem.find("a", href=True)

            if link:
                href = link.get("href")
                # Filter out non-company websites
                if href.startswith("http") and not any(
                    domain in href
                    for domain in [
                        "gamecompanies.com",
                        "gcinsider.com",
                        "facebook.com",
                        "twitter.com",
                        "linkedin.com",
                        "instagram.com",
                        "youtube.com",
                        "discord.com",
                        "google.com",
                    ]
                ):
                    website = href
                    break

        # Fallback: look for any external link
        if not website:
            for link in soup.find_all("a", href=True):
                href = link.get("href")

                if not href.startswith("http"):
                    continue
                if any(
                    domain in href
                    for domain in [
                        "gamecompanies.com",
                        "gcinsider.com",
                        "facebook.com",
                        "twitter.com",
                        "linkedin.com",
                        "instagram.com",
                        "youtube.com",
                        "discord.com",
                        "google.com",
                        "reddit.com",
                        "twitch.tv",
                    ]
                ):
                    continue

                website = href
                break

        return website

    except Exception as e:
        return None


def find_careers_page(company_name, website):
    """Try to find the careers/jobs page for a company"""

    careers_paths = [
        "/careers",
        "/jobs",
        "/career",
        "/work-with-us",
        "/join-us",
        "/opportunities",
        "/careers/jobs",
        "/about/careers",
        "/company/careers",
    ]

    try:
        for path in careers_paths:
            test_url = website.rstrip("/") + path
            try:
                response = requests.head(test_url, timeout=5, allow_redirects=True)
                if response.status_code == 200:
                    return test_url
            except:
                continue

        return website

    except:
        return website


def scrape_jobs(company_name, url):
    """Fetch webpage (following pagination) and have Claude analyze it for matching jobs"""

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    # Collect text from up to 3 pages
    all_page_text = []
    current_url = url
    visited = {url}

    for page_num in range(3):
        try:
            response = requests.get(current_url, headers=headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            all_page_text.append(soup.get_text(separator="\n", strip=True))

            # Look for a "Next" pagination link
            next_url = None
            for link in soup.find_all("a", href=True):
                text = link.get_text(strip=True).lower()
                if text in ("next", "next page", ">", "»", "next »", "› next"):
                    candidate = urljoin(current_url, link["href"])
                    if candidate not in visited:
                        next_url = candidate
                        break

            if not next_url:
                break
            visited.add(next_url)
            current_url = next_url
            time.sleep(1)

        except Exception as e:
            if page_num == 0:
                print(f"   ⚠️  Could not load page: {e}")
                return []
            break  # Pagination page failed — use what we have

    if len(all_page_text) > 1:
        print(f"   📄 Scraped {len(all_page_text)} pages of job listings")

    page_text = "\n\n".join(all_page_text)
    if len(page_text) > 100000:
        page_text = page_text[:100000]

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            max_tokens=2000,
            messages=[
                {
                    "role": "user",
                    "content": f"""Analyze this webpage from {company_name} and return a JSON object.

Find ALL job openings matching ANY of these criteria:
- UI Designer, UX Designer, UI/UX Designer, Product Designer, Visual Designer, Interaction Designer
- UX Researcher, User Researcher, Experience Designer
- Design Manager, UX Manager, UI Manager, Lead Designer, Principal Designer, Design Team Lead
- Art Director, Creative Director, Design Director, Game Director, Product Director
- Any role with "Experience" in the title
- Any role with both "Design" and "Manager" or "Lead"

Return this exact JSON structure:
{{
  "status": "has_jobs" | "no_open_roles" | "no_careers_page",
  "total_seen": <total number of job listings on page, 0 if none>,
  "matches": [
    {{"title": "...", "location": "...", "work_type": "Remote|Hybrid|On-site|Not specified", "url": "..."}}
  ]
}}

- "has_jobs": page has job listings (whether or not any match)
- "no_open_roles": careers page exists but no current openings
- "no_careers_page": page doesn't appear to be a jobs/careers page

Webpage text:
{page_text}""",
                }
            ],
        )

        response_text = response.choices[0].message.content.strip()

        # Extract JSON object from response
        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
        else:
            result = {"status": "unknown", "total_seen": 0, "matches": []}

        status = result.get("status", "unknown")
        total = result.get("total_seen", 0)
        matches = result.get("matches", [])

        if status == "no_careers_page":
            print(f"   ℹ️  No careers page detected")
        elif status == "no_open_roles":
            print(f"   ✓  Careers page found — no open roles currently")
        elif status == "has_jobs" and total > 0 and not matches:
            print(f"   ✓  Found {total} job(s) — none match the search criteria")

        return matches

    except Exception as e:
        print(f"   ⚠️  Error scraping {company_name}: {e}")
        return []


def save_to_excel(all_jobs, filename=None):
    """Save jobs to Excel file"""
    if not all_jobs:
        return None

    df = pd.DataFrame(all_jobs)

    # Reorder columns
    column_order = [
        "region",
        "company",
        "title",
        "work_type",
        "location",
        "url",
        "company_website",
        "date_found",
    ]
    df = df[column_order]

    df.to_excel(filename, index=False)
    return filename


# ── TEST MODE ──────────────────────────────────────────────
TEST_MODE = False  # Set to False for the full run
TEST_LIMIT = 5  # How many companies to check in test mode
# ────────────────────────────────────────────────────────────

# Main execution
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🎮 GAME INDUSTRY JOB SEARCH")
    print("=" * 60)
    print("Regions: Canada + United States + England")
    print("\nLooking for:")
    print("  • UI/UX/Design roles")
    print("  • Design Managers & Leads")
    print("  • Director positions")
    print("  • Experience-related roles")
    print("\nTracking: Remote, Hybrid, On-site")
    print("=" * 60 + "\n")

    # Get companies from all regions
    all_profiles = []

    # Canadian companies
    canadian_url = "https://gamecompanies.com/industries/north-america/canadian-game-industry/companies"
    canadian_profiles = get_all_company_profiles(canadian_url, "Canada")
    all_profiles.extend(canadian_profiles)

    # US companies
    us_url = "https://gamecompanies.com/industries/north-america/american-game-industry/companies"
    us_profiles = get_all_company_profiles(us_url, "United States")
    all_profiles.extend(us_profiles)

    # English companies
    england_url = (
        "https://gamecompanies.com/industries/europe/english-game-industry/companies"
    )
    england_profiles = get_all_company_profiles(england_url, "England")
    all_profiles.extend(england_profiles)

    if not all_profiles:
        print("❌ No companies found. Exiting.")
        exit()

    if TEST_MODE:
        all_profiles = all_profiles[:TEST_LIMIT]
        print(f"\n⚠️  TEST MODE: checking first {TEST_LIMIT} companies only")
    else:
        print(f"\n📋 Total companies to check: {len(all_profiles)}")
        print(f"   • Canada: {len(canadian_profiles)}")
        print(f"   • United States: {len(us_profiles)}")
        print(f"   • England: {len(england_profiles)}")
        print(f"\n⏱️  Estimated time: ~{len(all_profiles) * 4 // 60} minutes")
    print("=" * 60 + "\n")

    all_jobs = []
    companies_with_websites = 0
    output_file = f"game_industry_jobs_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"

    # Check each company
    for i, profile in enumerate(all_profiles, 1):
        print(f"\n[{i}/{len(all_profiles)}] {profile['name']} ({profile['region']})")

        # Get website
        website = get_company_website(profile["profile_url"])

        if not website:
            print(f"   ⚠️  No website found")
            time.sleep(1)
            continue

        companies_with_websites += 1
        print(f"   🌐 {website}")

        # Find careers page
        careers_url = find_careers_page(profile["name"], website)
        if careers_url != website:
            print(f"   💼 Careers: {careers_url}")

        # Scrape for jobs
        jobs = scrape_jobs(profile["name"], careers_url)

        if jobs:
            print(f"   ✅ Found {len(jobs)} matching jobs!")
            for job in jobs:
                work_indicator = (
                    f" [{job.get('work_type', 'Not specified')}]"
                    if job.get("work_type")
                    else ""
                )
                print(f"      • {job.get('title', 'N/A')}{work_indicator}")

        # Add metadata
        for job in jobs:
            job["company"] = profile["name"]
            job["region"] = profile["region"]
            job["company_website"] = website
            job["date_found"] = datetime.now().strftime("%Y-%m-%d")
            if "location" not in job:
                job["location"] = "Not specified"
            if "work_type" not in job:
                job["work_type"] = "Not specified"
            if "url" not in job:
                job["url"] = careers_url

        all_jobs.extend(jobs)

        # Auto-save every 5 companies
        if i % 5 == 0 and all_jobs:
            save_to_excel(all_jobs, output_file)
            print(f"   💾 Auto-saved {len(all_jobs)} jobs → {output_file}")

        time.sleep(3)

    # Final save
    filename = save_to_excel(all_jobs, output_file)
    if filename:
        print(f"\n✅ Saved {len(all_jobs)} jobs to {filename}")
    else:
        print("\n⚠️  No jobs found")

    # Summary
    print("\n" + "=" * 60)
    print("📊 FINAL SUMMARY")
    print("=" * 60)
    print(f"Total companies checked: {len(all_profiles)}")
    print(f"  • Canada: {len(canadian_profiles)}")
    print(f"  • United States: {len(us_profiles)}")
    print(f"  • England: {len(england_profiles)}")
    print(f"Companies with websites: {companies_with_websites}")
    print(f"Total matching jobs found: {len(all_jobs)}")

    # Remote/Hybrid breakdown
    if all_jobs:
        remote_count = sum(1 for job in all_jobs if job.get("work_type") == "Remote")
        hybrid_count = sum(1 for job in all_jobs if job.get("work_type") == "Hybrid")
        onsite_count = sum(1 for job in all_jobs if job.get("work_type") == "On-site")

        print(f"\nWork Type Breakdown:")
        print(f"  • Remote: {remote_count}")
        print(f"  • Hybrid: {hybrid_count}")
        print(f"  • On-site: {onsite_count}")
        print(
            f"  • Not specified: {len(all_jobs) - remote_count - hybrid_count - onsite_count}"
        )

        # Regional breakdown
        print(f"\nJobs by Region:")
        canada_jobs = sum(1 for job in all_jobs if job.get("region") == "Canada")
        us_jobs = sum(1 for job in all_jobs if job.get("region") == "United States")
        england_jobs = sum(1 for job in all_jobs if job.get("region") == "England")
        print(f"  • Canada: {canada_jobs}")
        print(f"  • United States: {us_jobs}")
        print(f"  • England: {england_jobs}")

    print("=" * 60)

    if all_jobs:
        print("\nTop companies with openings:")
        company_counts = {}
        for job in all_jobs:
            company_counts[job["company"]] = company_counts.get(job["company"], 0) + 1

        for company, count in sorted(
            company_counts.items(), key=lambda x: x[1], reverse=True
        )[:10]:
            print(f"  • {company}: {count} job(s)")

        if filename:
            print(f"\n💾 Results saved to: {filename}")
