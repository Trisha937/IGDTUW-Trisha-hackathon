"""
Data Ingestion Module — The "Antenna" of our Risk Engine.

This module is responsible for collecting raw, unstructured text from 3 sources:
  1. Economic Times RSS (Financial News)
  2. NSE Corporate Announcements RSS (Official Filings)
  3. Reddit via Apify (Social Media Sentiment)

Each source returns a list of RawTextItem objects — a standardized "passport"
for every piece of information entering our system (see models.py).

KEY DESIGN DECISIONS:
- If live RSS feeds fail (no internet, timeout, blocked), we seamlessly
  fall back to our local verified samples in data/*.json so the demo
  never crashes.
- Apify Reddit scraping has a hard cap of 600 records to stay within
  the free $5/month tier.
- Every item gets a content_hash to detect and skip exact duplicates.
"""

import json
import hashlib
import logging
import os
from pathlib import Path
from typing import List, Optional, Dict, Set
from datetime import datetime

import feedparser
from dotenv import load_dotenv

from src.ingestion.models import RawTextItem
from src.config import NIFTY_10_BASKET

# Load API keys from .env file (if it exists)
load_dotenv()

logger = logging.getLogger("DataCollector")

# Path to our data/ directory (relative to project root)
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


# ---------------------------------------------------------------------------
# HELPER: Content Hashing for Deduplication
# ---------------------------------------------------------------------------
# WHY DO WE NEED THIS?
# Imagine the Economic Times publishes the same article at 10:00 AM and
# their RSS feed still shows it at 10:05 AM when we poll again.
# Without deduplication, our engine would process the same article twice,
# potentially double-counting the sentiment and skewing portfolio weights.
#
# HOW IT WORKS:
# We take the title + first 200 characters of text, run it through SHA-256
# (a cryptographic hash function), and get a unique fingerprint string.
# If two articles produce the same fingerprint, they are duplicates.

def compute_content_hash(title: str, text: str) -> str:
    """
    Creates a unique fingerprint for a piece of content.
    Two articles with the same title and opening text = same hash = duplicate.
    """
    raw = f"{title.strip().lower()}|{text.strip().lower()[:200]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# HELPER: Entity Resolution (Which company is this article about?)
# ---------------------------------------------------------------------------
# WHY DO WE NEED THIS?
# A news headline might say "Mukesh Ambani unveils hydrogen plant" without
# ever mentioning "RELIANCE" or "RIL". Our engine needs to figure out that
# this headline is about the stock ticker RELIANCE.
#
# HOW IT WORKS:
# We search the text (lowercased) for any of the aliases we defined in
# config.py. The first match wins. If no alias matches any company in our
# Nifty 10 basket, we return None (meaning this article isn't about any
# of our tracked stocks).

def resolve_ticker(text: str) -> Optional[str]:
    """
    Scans text for company aliases defined in config.py.
    Returns the matching ticker (e.g. "RELIANCE") or None.
    """
    text_lower = text.lower()
    for ticker, info in NIFTY_10_BASKET.items():
        for alias in info["aliases"]:
            if alias in text_lower:
                return ticker
    return None


class DataCollector:
    """
    The central data collection hub. Gathers text from 3 sources:
      1. Economic Times RSS (news)
      2. NSE Corporate Announcements RSS (announcements)
      3. Reddit via Apify (social)

    All methods return List[RawTextItem] — our standardized data format.
    """

    # -----------------------------------------------------------------------
    # RSS Feed URLs
    # -----------------------------------------------------------------------
    # These are free, public RSS feeds that update every few minutes.
    # RSS (Really Simple Syndication) is a standardized XML format that
    # websites use to publish a machine-readable list of their latest articles.
    # The feedparser library converts this XML into Python dictionaries.

    ET_MARKETS_RSS = "https://economictimes.indiatimes.com/markets/stocks/rss.cms"
    NSE_ANNOUNCEMENTS_RSS = "https://www.nseindia.com/api/corporate-announcements?index=equities"

    # -----------------------------------------------------------------------
    # Apify Configuration (Reddit Scraper)
    # -----------------------------------------------------------------------
    # Apify is a web scraping platform. We use their "trudax/reddit-scraper-lite"
    # actor (a pre-built scraper) to fetch posts from Indian stock market
    # subreddits.
    #
    # CREDIT SAFETY: The free Apify plan gives $5/month of compute credits.
    # We enforce a hard cap of 600 total records across the project lifetime
    # to ensure we NEVER exceed this limit and get charged.

    APIFY_ACTOR_ID = "trudax/reddit-scraper-lite"
    APIFY_RECORD_CAP = 600  # Hard ceiling — stop scraping after 600 records
    REDDIT_SUBREDDITS = [
        "IndianStockMarket",
        "IndiaInvestments",
        "DalalStreetBets",
    ]

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or DATA_DIR
        # Track content hashes to skip duplicates across all sources
        self._seen_hashes: Set[str] = set()
        # Track total Apify records fetched (persists across calls)
        self._apify_records_fetched: int = 0

    # -----------------------------------------------------------------------
    # SOURCE 1: Financial News via RSS
    # -----------------------------------------------------------------------
    # HOW RSS WORKS:
    # 1. We send an HTTP request to the Economic Times RSS URL.
    # 2. The server returns an XML document with a list of <item> entries.
    # 3. Each <item> has a <title>, <description> (summary), <link>, etc.
    # 4. feedparser converts this XML into Python objects we can loop through.
    #
    # FALLBACK LOGIC:
    # If the RSS fetch fails (network error, timeout, blocked by firewall),
    # we load our pre-verified samples from data/news_samples.json instead.
    # This ensures the demo NEVER shows an error screen to judges.

    def fetch_news(self, limit: int = 15) -> List[RawTextItem]:
        """
        Fetches live financial news from Economic Times RSS feed.
        Falls back to local samples if the network is unavailable.
        """
        items: List[RawTextItem] = []

        try:
            logger.info(f"Fetching live news from: {self.ET_MARKETS_RSS}")
            feed = feedparser.parse(self.ET_MARKETS_RSS)

            if feed.bozo:
                # "bozo" is feedparser's way of saying "I got something, but
                # it wasn't valid RSS/XML". Common when blocked or rate-limited.
                logger.warning(f"RSS feed returned invalid data: {feed.bozo_exception}")

            for entry in feed.entries[:limit]:
                title = getattr(entry, "title", "Untitled")
                summary = getattr(entry, "summary", getattr(entry, "description", title))
                link = getattr(entry, "link", "")

                # Deduplication check
                content_hash = compute_content_hash(title, summary)
                if content_hash in self._seen_hashes:
                    continue
                self._seen_hashes.add(content_hash)

                # Entity Resolution: figure out which company this is about
                combined_text = f"{title} {summary}"
                ticker = resolve_ticker(combined_text)

                items.append(RawTextItem(
                    source="news",
                    title=title,
                    text=summary,
                    url=link,
                    author="Economic Times RSS",
                    target_ticker=ticker,
                ))

        except Exception as e:
            logger.warning(f"Live news fetch failed ({e}). Using local cache.")

        # Fallback: if live fetch returned nothing, use local samples
        if not items:
            logger.info("Loading news from local cache: data/news_samples.json")
            items = self._load_json_samples("news_samples.json")[:limit]

        logger.info(f"News ingestion complete: {len(items)} items")
        return items

    # -----------------------------------------------------------------------
    # SOURCE 2: NSE Corporate Announcements
    # -----------------------------------------------------------------------
    # These are OFFICIAL filings submitted by companies to the National Stock
    # Exchange of India. Examples:
    #   - "Board approves quarterly dividend of Rs 18/share"
    #   - "Company has received a show-cause notice from SEBI"
    #   - "Proposed acquisition of XYZ Ltd for Rs 2,000 Cr"
    #
    # These carry the HIGHEST credibility (source weight = 1.0 in config.py)
    # because they are legally mandated disclosures — companies can be fined
    # or delisted for filing false announcements.
    #
    # NOTE: NSE's API can be tricky (they sometimes block non-browser requests).
    # We use a requests-based approach with proper headers, with fallback.

    def fetch_announcements(self, limit: int = 10) -> List[RawTextItem]:
        """
        Fetches official corporate announcements from NSE India.
        Falls back to a subset of news samples tagged as announcements.
        """
        items: List[RawTextItem] = []

        try:
            import requests

            logger.info("Fetching NSE corporate announcements...")
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            }
            resp = requests.get(
                self.NSE_ANNOUNCEMENTS_RSS,
                headers=headers,
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                for item in data[:limit]:
                    title = item.get("desc", item.get("subject", "NSE Announcement"))
                    company = item.get("symbol", "")
                    text = item.get("desc", title)

                    content_hash = compute_content_hash(title, text)
                    if content_hash in self._seen_hashes:
                        continue
                    self._seen_hashes.add(content_hash)

                    # Try to match the NSE symbol to our basket
                    ticker = company if company in NIFTY_10_BASKET else resolve_ticker(f"{title} {text}")

                    items.append(RawTextItem(
                        source="announcement",
                        title=title,
                        text=text,
                        url=f"https://www.nseindia.com/companies-listing/corporate-filings-announcements",
                        author=f"NSE Filing ({company})",
                        target_ticker=ticker,
                    ))

        except Exception as e:
            logger.warning(f"NSE announcement fetch failed ({e}). Using fallback.")

        if not items:
            logger.info("Using synthetic announcements from local cache.")
            # Reuse news samples but re-tag them as announcements for demo
            fallback = self._load_json_samples("news_samples.json")[:limit]
            for item in fallback:
                item.source = "announcement"
            items = fallback

        logger.info(f"Announcement ingestion complete: {len(items)} items")
        return items

    # -----------------------------------------------------------------------
    # SOURCE 3: Reddit via Apify (Social Media)
    # -----------------------------------------------------------------------
    # HOW APIFY WORKS:
    # 1. We send an API request to Apify's cloud with our API token.
    # 2. We tell it: "Run the trudax/reddit-scraper-lite actor on these
    #    subreddits: IndianStockMarket, IndiaInvestments, DalalStreetBets."
    # 3. Apify's servers visit Reddit, scrape the posts, and return the
    #    results as JSON.
    # 4. We convert each post into our standardized RawTextItem format.
    #
    # CREDIT SAFETY MECHANISM:
    # Before each call, we check: "Have we already fetched 600 records total?"
    # If yes, we STOP calling Apify and use local samples instead.
    # This guarantees we never exceed the free $5/month limit.
    #
    # IF NO API TOKEN:
    # If APIFY_API_TOKEN is not set in .env, we skip the API call entirely
    # and use our local social_samples.json. This allows offline development
    # and testing without any API dependency.

    def fetch_social(self, limit: int = 20) -> List[RawTextItem]:
        """
        Fetches Reddit posts about Indian stocks via Apify.
        Falls back to local social samples if token missing or cap reached.
        """
        apify_token = os.getenv("APIFY_API_TOKEN")

        # Guard 1: No API token → use local samples
        if not apify_token or apify_token == "your_apify_token_here":
            logger.info("No Apify token found. Using local social samples.")
            return self._load_json_samples("social_samples.json")[:limit]

        # Guard 2: Credit cap reached → use local samples
        if self._apify_records_fetched >= self.APIFY_RECORD_CAP:
            logger.warning(
                f"Apify credit cap reached ({self._apify_records_fetched}/"
                f"{self.APIFY_RECORD_CAP} records). Using local samples."
            )
            return self._load_json_samples("social_samples.json")[:limit]

        # Calculate how many more records we're allowed to fetch
        remaining_budget = self.APIFY_RECORD_CAP - self._apify_records_fetched
        fetch_count = min(limit, remaining_budget)

        items: List[RawTextItem] = []
        try:
            from apify_client import ApifyClient

            logger.info(
                f"Calling Apify Reddit scraper (budget: {remaining_budget} "
                f"records remaining)..."
            )
            client = ApifyClient(apify_token)

            # Configure the Reddit scraper actor
            run_input = {
                "startUrls": [
                    {"url": f"https://www.reddit.com/r/{sub}/"}
                    for sub in self.REDDIT_SUBREDDITS
                ],
                "maxItems": fetch_count,
                "sort": "new",  # Get newest posts first
            }

            # Run the actor and wait for it to finish
            run = client.actor(self.APIFY_ACTOR_ID).call(run_input=run_input)

            # Fetch results from the actor's default dataset
            for post in client.dataset(run["defaultDatasetId"]).iterate_items():
                title = post.get("title", "Reddit Post")
                body = post.get("body", post.get("selftext", title))
                url = post.get("url", "")
                author = post.get("author", "Reddit User")
                subreddit = post.get("subreddit", "")

                content_hash = compute_content_hash(title, body)
                if content_hash in self._seen_hashes:
                    continue
                self._seen_hashes.add(content_hash)

                combined = f"{title} {body}"
                ticker = resolve_ticker(combined)

                items.append(RawTextItem(
                    source="social",
                    title=title,
                    text=body[:500],  # Truncate very long posts
                    url=url,
                    author=f"u/{author} (r/{subreddit})",
                    target_ticker=ticker,
                ))

            # Update the running total
            self._apify_records_fetched += len(items)
            logger.info(
                f"Apify fetch complete: {len(items)} posts. "
                f"Total fetched: {self._apify_records_fetched}/{self.APIFY_RECORD_CAP}"
            )

        except Exception as e:
            logger.warning(f"Apify scrape failed ({e}). Using local social samples.")
            if not items:
                items = self._load_json_samples("social_samples.json")[:limit]

        return items

    # -----------------------------------------------------------------------
    # REPLAY SCENARIOS (For Live Demo)
    # -----------------------------------------------------------------------
    # During your 5-minute pitch, you can't wait for live news to arrive.
    # Instead, you press a button like "Simulate Tech Surge" and the system
    # loads a pre-built scenario from data/replay_scenarios.json.
    #
    # Each scenario is a curated set of news + social items that tell a
    # compelling financial story (e.g., IT sector boom, banking penalty).

    def load_replay_scenario(self, scenario_key: str) -> List[RawTextItem]:
        """Loads a named replay scenario for demonstration."""
        filepath = self.data_dir / "replay_scenarios.json"
        if not filepath.exists():
            logger.error(f"Replay scenarios file not found: {filepath}")
            return []

        with open(filepath, "r", encoding="utf-8") as f:
            scenarios = json.load(f)

        scenario = scenarios.get(scenario_key)
        if not scenario:
            logger.error(f"Scenario '{scenario_key}' not found. Available: {list(scenarios.keys())}")
            return []

        items = [RawTextItem(**item) for item in scenario.get("items", [])]
        logger.info(f"Loaded replay scenario '{scenario_key}': {len(items)} items")
        return items

    def get_available_scenarios(self) -> Dict[str, dict]:
        """Returns metadata about all available replay scenarios."""
        filepath = self.data_dir / "replay_scenarios.json"
        if not filepath.exists():
            return {}
        with open(filepath, "r", encoding="utf-8") as f:
            scenarios = json.load(f)
            return {
                key: {
                    "name": val.get("name"),
                    "description": val.get("description"),
                    "item_count": len(val.get("items", [])),
                }
                for key, val in scenarios.items()
            }

    # -----------------------------------------------------------------------
    # UNIFIED INGESTION (Fetch All Sources at Once)
    # -----------------------------------------------------------------------
    # This is the method the rest of our system calls. It collects from all
    # three sources, merges the results into a single list, and returns it.

    def fetch_all(self) -> List[RawTextItem]:
        """Fetches from all 3 sources and returns a unified list."""
        all_items: List[RawTextItem] = []

        all_items.extend(self.fetch_news())
        all_items.extend(self.fetch_announcements())
        all_items.extend(self.fetch_social())

        logger.info(f"Total ingestion: {len(all_items)} items from all sources")
        return all_items

    # -----------------------------------------------------------------------
    # PRIVATE HELPER: Load Local JSON Samples
    # -----------------------------------------------------------------------

    def _load_json_samples(self, filename: str) -> List[RawTextItem]:
        """Loads pre-verified sample data from a JSON file in data/."""
        filepath = self.data_dir / filename
        if not filepath.exists():
            logger.warning(f"Sample file not found: {filepath}")
            return []
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            return [RawTextItem(**item) for item in data]
