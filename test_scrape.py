import json
import os
import re
import time
from datetime import datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

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
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=options
    )

    try:
        driver.get(url)
        time.sleep(3)

        # Keep clicking "Load More" until it's gone
        click_count = 0
        while True:
            try:
                load_more = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located(
                        (
                            By.XPATH,
                            "//button[contains(text(), 'Load') or contains(text(), 'More') or contains(@class, 'load')]",
                        )
                    )
                )

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
        soup = BeautifulSoup(driver.page_source, "html.parser")
        driver.quit()

        # Find all company profile links
        company_profiles = []
        seen_urls = set()

        for link in soup.find_all("a", href=True):
            href = link.get("href", "")

            # Look for company profile links (deep paths with 'industries')
            if (
                "industries" in href
                and href.count("/") >= 6
                and not href.endswith("/companies")
            ):
                full_url = (
                    "https://gamecompanies.com" + href if href.startswith("/") else href
                )

                if full_url in seen_urls:
                    continue

                # Get company name
                company_name = link.get_text(strip=True)

                # Skip navigation links and empty names
                if not company_name or len(company_name) < 2:
                    continue
                if company_name.lower() in [
                    "industries",
                    "jobs",
                    "games",
                    "north america",
                    "south america",
                    "europe",
                    "asia",
                    "africa",
                    "oceania",
                    "regions",
                    "cities",
                    "companies",
                ]:
                    continue

                # IMPROVED NAME CLEANING
                # Remove common suffixes that get attached
                # Pattern: "Company NameExtra text" where Extra starts with capital or common words

                # First, try to find where the actual name ends
                # Look for patterns like "StudioXXX" or "GamesXXX" where XXX is a capital letter or description
                for separator in [
                    "Studio",
                    "Games",
                    "Interactive",
                    "Entertainment",
                    "Digital",
                    "Media",
                    "Inc",
                    "Ltd",
                ]:
                    # Find if separator exists and is followed by a capital letter (not a space)
                    pattern = separator + r"(?=[A-Z])"
                    match = re.search(pattern, company_name)
                    if match:
                        # Cut off everything after separator
                        company_name = company_name[: match.end()].strip()
                        break

                # Remove everything after common description starters
                for pattern in [
                    "We ",
                    "A ",
                    "An ",
                    "The ",
                    "Creating",
                    "Making",
                    "Building",
                    "Developing",
                    "Connecting",
                ]:
                    if pattern in company_name:
                        idx = company_name.index(pattern)
                        if (
                            idx > 0
                        ):  # Make sure we're not cutting off "The" from the beginning
                            company_name = company_name[:idx].strip()
                            break

                # Use regex to catch pattern "NameDescriptionText"
                # This catches "A.C.R.O.N.Y.M. GamesConnecting the dots" -> "A.C.R.O.N.Y.M. Games"
                match = re.match(
                    r"^(.+?(?:Studio|Studios|Games|Interactive|Entertainment|Digital|Media|Inc|Ltd|LLC))(?=[A-Z][a-z])",
                    company_name,
                )
                if match:
                    company_name = match.group(1).strip()

                # Fallback: if name is still super long, take first reasonable chunk
                if len(company_name) > 60:
                    # Try to find a natural break
                    words = company_name.split()
                    # Take words until we hit a likely description start
                    clean_words = []
                    for word in words:
                        clean_words.append(word)
                        # Stop if we hit a description word
                        if word.lower() in [
                            "we",
                            "a",
                            "an",
                            "the",
                            "creating",
                            "making",
                            "building",
                        ]:
                            clean_words.pop()  # Remove the description word
                            break
                        # Or if we have enough words and hit max length
                        if len(" ".join(clean_words)) > 50 and len(clean_words) >= 2:
                            break
                    company_name = " ".join(clean_words)

                if company_name and full_url not in seen_urls:
                    company_profiles.append(
                        {
                            "name": company_name,
                            "profile_url": full_url,
                            "region": region_name,
                        }
                    )
                    seen_urls.add(full_url)

        print(f"   Found {len(company_profiles)} {region_name} company profiles")
        print(f"   First few: {', '.join([p['name'] for p in company_profiles[:5]])}\n")

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
    """Fetch webpage and have Claude analyze it for matching jobs"""

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        page_text = soup.get_text(separator="\n", strip=True)

        max_chars = 100000
        if len(page_text) > max_chars:
            page_text = page_text[:max_chars]

        response = client.chat.completions.create(
            model="deepseek-chat",
            max_tokens=2000,
            messages=[
                {
                    "role": "user",
                    "content": f"""Analyze this webpage from {company_name} and find ALL job openings that match ANY of these criteria:

**UI/UX/Design Roles:**
- UI Designer, UX Designer, UI/UX Designer
- User Interface Designer, User Experience Designer
- Product Designer, Interaction Designer
- Visual Designer, Experience Designer
- UX Researcher, User Researcher

**Design Management:**
- Design Manager, UX Manager, UI Manager
- Lead Designer, Principal Designer
- Design Team Lead

**Director Roles:**
- Art Director, Creative Director, Design Director
- Game Director, Product Director
- Director of Design, Director of UX

**Other:**
- Any role with "Experience" in the title
- Any role with "Design" and "Manager" or "Lead"

For each matching job, extract:
- title: The exact job title
- location: Where the job is located (if mentioned)
- work_type: Set to "Remote" if remote is mentioned, "Hybrid" if hybrid is mentioned, "On-site" if neither, or "Not specified" if unclear
- url: The direct link to apply if available

Return ONLY a valid JSON array with these exact fields: title, location, work_type, url
If no jobs found, return []

Webpage text:
{page_text}""",
                }
            ],
        )

        response_text = response.choices[0].message.content.strip()

        if response_text.startswith("["):
            jobs = json.loads(response_text)
        else:
            json_match = re.search(r"\[.*\]", response_text, re.DOTALL)
            if json_match:
                jobs = json.loads(json_match.group())
            else:
                jobs = []

        return jobs

    except Exception as e:
        return []


def save_to_excel(all_jobs):
    """Save jobs to Excel file"""
    if not all_jobs:
        print("\n⚠️  No jobs found")
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

    filename = f"game_industry_jobs_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    df.to_excel(filename, index=False)
    print(f"\n✅ Saved {len(all_jobs)} jobs to {filename}")
    return filename


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

    print(f"\n📋 Total companies to check: {len(all_profiles)}")
    print(f"   • Canada: {len(canadian_profiles)}")
    print(f"   • United States: {len(us_profiles)}")
    print(f"   • England: {len(england_profiles)}")
    print(f"\n⏱️  Estimated time: ~{len(all_profiles) * 4 // 60} minutes")
    print("=" * 60 + "\n")

    input("Press ENTER to start checking companies (or Ctrl+C to cancel)...")

    all_jobs = []
    companies_with_websites = 0

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
        time.sleep(3)

    # Save results
    filename = save_to_excel(all_jobs)

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
