#!/usr/bin/env python3
"""
Job Market Intelligence Corpus — Data Collection Script

Collects job postings for data roles from StepStone (DE), Indeed (DE),
and LinkedIn using HTTP requests + BeautifulSoup HTML parsing.

Usage:
    python3 01_collect_job_postings.py --source stepstone --city Berlin --pages 10
    python3 01_collect_job_postings.py --source indeed --city Munich --pages 10

Requirements: requests, beautifulsoup4, lxml, pandas
    pip install requests beautifulsoup4 lxml pandas
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random
import argparse
import logging
import os
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Target role keywords (bilingual, as used in the study)
ROLE_KEYWORDS = [
    "Data Analyst", "Data Engineer", "BI Engineer", "Data Scientist",
    "Werkstudent Data", "Praktikum Analytics", "Analytics Engineer"
]

TARGET_CITIES = [
    "Berlin", "Munich", "Hamburg", "Frankfurt", "Cologne",
    "Essen", "Dortmund", "Stuttgart", "Leipzig", "Nuremberg", "Düsseldorf"
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/115.0",
]

OUTPUT_SCHEMA = [
    "posting_id", "title_clean", "employer", "city",
    "contract_type", "posted_date", "source",
    "seniority", "description_raw", "description_clean",
    "skills_extracted", "cluster_id", "cluster_name", "num_skills"
]


def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.google.de/",
    }


def polite_delay():
    """Randomised delay 2–8 seconds to avoid rate limiting (as documented in thesis Section 6)."""
    t = random.uniform(2.0, 8.0)
    logger.debug(f"Waiting {t:.1f}s...")
    time.sleep(t)


def clean_text(raw_html: str) -> str:
    """Strip HTML tags, normalise whitespace, preserve German umlauts."""
    soup = BeautifulSoup(raw_html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    text = " ".join(text.split())
    return text


def scrape_stepstone(keyword: str, city: str, pages: int = 5) -> list[dict]:
    """
    Scrape StepStone Germany for job postings.
    CSS selectors valid as of Jan 2024 (structure changed twice during collection —
    multiple fallback selectors implemented as documented in thesis Table 6).
    """
    results = []
    base_url = "https://www.stepstone.de/jobs/{keyword}/in-{city}"
    url = base_url.format(keyword=keyword.replace(" ", "-"), city=city)

    for page in range(1, pages + 1):
        try:
            logger.info(f"StepStone | {keyword} | {city} | page {page}")
            params = {"page": page}
            resp = requests.get(url, headers=get_headers(), params=params, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            # Multiple fallback selectors (StepStone updated layout twice during collection)
            cards = (
                soup.select("article.res-1r9adp7")
                or soup.select("article[data-at='job-item']")
                or soup.select("div.js-job-item")
            )
            if not cards:
                logger.warning(f"No cards found on page {page} — structure may have changed")
                break

            for card in cards:
                title_el = card.select_one("h2 a, span.res-nehv70, a[data-at='job-item-title']")
                employer_el = card.select_one("span[data-at='job-item-company-name'], div.res-gyj0fl")
                date_el = card.select_one("time, span[data-at='job-item-date']")
                link_el = card.select_one("a[href*='/stellenangebote']")

                if not title_el:
                    continue

                posting = {
                    "title_raw": title_el.get_text(strip=True),
                    "employer": employer_el.get_text(strip=True) if employer_el else "",
                    "city": city,
                    "contract_type": _infer_contract(title_el.get_text(strip=True), keyword),
                    "posted_date": date_el.get("datetime", "")[:10] if date_el else "",
                    "source": "StepStone",
                    "url": "https://www.stepstone.de" + link_el["href"] if link_el else "",
                }
                results.append(posting)

            polite_delay()

        except requests.RequestException as e:
            logger.error(f"Request error on page {page}: {e}")
            polite_delay()
            continue

    return results


def scrape_indeed(keyword: str, city: str, pages: int = 5) -> list[dict]:
    """
    Scrape Indeed Germany. CAPTCHA triggered after rapid sequential requests —
    resolved with randomised delays and user-agent rotation (thesis Section 6).
    """
    results = []
    base_url = "https://de.indeed.com/jobs"

    for page in range(pages):
        try:
            logger.info(f"Indeed | {keyword} | {city} | start={page*10}")
            params = {"q": keyword, "l": city, "start": page * 10, "fromage": "30"}
            resp = requests.get(base_url, headers=get_headers(), params=params, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            cards = soup.select("div.job_seen_beacon") or soup.select("div[data-testid='slider_item']")
            if not cards:
                logger.warning(f"No job cards found at start={page*10}")
                break

            for card in cards:
                title_el = card.select_one("h2.jobTitle span[title], h2.jobTitle a")
                employer_el = card.select_one("span.companyName, [data-testid='company-name']")
                date_el = card.select_one("span.date, [data-testid='myJobsStateDate']")
                contract_el = card.select_one("div.metadata span.attribute_snippet")

                if not title_el:
                    continue

                posting = {
                    "title_raw": title_el.get_text(strip=True),
                    "employer": employer_el.get_text(strip=True) if employer_el else "",
                    "city": city,
                    "contract_type": _infer_contract(title_el.get_text(strip=True), keyword),
                    "posted_date": _parse_indeed_date(date_el.get_text(strip=True) if date_el else ""),
                    "source": "Indeed Germany",
                    "url": "",
                }
                results.append(posting)

            polite_delay()

        except requests.RequestException as e:
            logger.error(f"Request error: {e}")
            polite_delay()

    return results


def _infer_contract(title: str, keyword: str) -> str:
    title_lower = title.lower()
    keyword_lower = keyword.lower()
    if "werkstudent" in title_lower or "werkstudent" in keyword_lower:
        return "Werkstudent"
    elif "praktik" in title_lower or "intern" in title_lower:
        return "Praktikum"
    elif "freelance" in title_lower or "contract" in title_lower:
        return "Freelance/Contract"
    else:
        return "Full-time"


def _parse_indeed_date(raw: str) -> str:
    """Convert Indeed relative dates to ISO format (approximate)."""
    from datetime import datetime, timedelta
    today = datetime.today()
    raw = raw.lower().strip()
    if "heute" in raw or "today" in raw or "gerade" in raw:
        return today.strftime("%Y-%m-%d")
    elif "gestern" in raw or "yesterday" in raw:
        return (today - timedelta(days=1)).strftime("%Y-%m-%d")
    elif "vor" in raw and "tag" in raw:
        try:
            days = int("".join(filter(str.isdigit, raw)))
            return (today - timedelta(days=days)).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return today.strftime("%Y-%m-%d")


def main():
    parser = argparse.ArgumentParser(description="Collect German tech job postings.")
    parser.add_argument("--source", choices=["stepstone", "indeed", "all"], default="all")
    parser.add_argument("--city", default="all", help="City name or 'all'")
    parser.add_argument("--pages", type=int, default=5)
    parser.add_argument("--output", default="data/job_postings_raw.csv")
    args = parser.parse_args()

    cities = TARGET_CITIES if args.city == "all" else [args.city]
    all_records = []

    for city in cities:
        for keyword in ROLE_KEYWORDS:
            if args.source in ("stepstone", "all"):
                all_records.extend(scrape_stepstone(keyword, city, args.pages))
            if args.source in ("indeed", "all"):
                all_records.extend(scrape_indeed(keyword, city, args.pages))

    df = pd.DataFrame(all_records)
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    df.to_csv(args.output, index=False, encoding="utf-8-sig")
    logger.info(f"Saved {len(df)} raw records to {args.output}")
    logger.info("Next step: run 02_deduplicate_clean.py")


if __name__ == "__main__":
    main()
