import requests
import logging
import time
import os
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SUBREDDITS = [
    "deals",
    "restaurant",
    "fastfood",
    "UberEATS",
    "doordash",
    "GrubHub",
    "freebies",
    "frugal",
]

SEARCH_QUERIES = {
    "deals": "restaurant food delivery coupon promo BOGO",
    "restaurant": "deal coupon discount promo special offer",
    "fastfood": "deal coupon promo free BOGO app offer",
    "UberEATS": "promo code coupon discount deal free delivery",
    "doordash": "promo code coupon deal discount free delivery",
    "GrubHub": "promo code coupon deal discount free",
    "freebies": "free food restaurant sample meal",
    "frugal": "restaurant food delivery deal coupon promo",
}

HEADERS = {"User-Agent": "adrian-deal-bot/1.0"}

MAX_AGE_HOURS = 24


def fetch_reddit_deals(limit_per_sub: int = 25) -> list[dict]:
    """Fetch deals from Reddit public JSON endpoints. No credentials needed.
    Only returns posts from the last 24 hours."""
    all_deals = []
    cutoff = time.time() - (MAX_AGE_HOURS * 3600)

    for subreddit in SUBREDDITS:
        query = SEARCH_QUERIES.get(subreddit, "deal discount coupon")
        url = f"https://www.reddit.com/r/{subreddit}/search.json"
        params = {"q": query, "sort": "new", "limit": limit_per_sub, "restrict_sr": "on"}

        try:
            response = requests.get(url, headers=HEADERS, params=params, timeout=10)
            response.raise_for_status()
            posts = response.json()["data"]["children"]

            fresh = 0
            for post in posts:
                data = post["data"]
                created = data.get("created_utc", 0)
                if created < cutoff:
                    continue
                fresh += 1
                age_hours = (time.time() - created) / 3600
                all_deals.append({
                    "id": data["id"],
                    "title": data["title"],
                    "body": data.get("selftext", ""),
                    "url": data.get("url", ""),
                    "source": "reddit",
                    "subreddit": subreddit,
                    "created_utc": created,
                    "age_hours": round(age_hours, 1),
                })

            logger.info(f"r/{subreddit}: {fresh}/{len(posts)} posts within {MAX_AGE_HOURS}h")

        except Exception as e:
            logger.error(f"r/{subreddit}: failed — {e}")
            continue

    logger.info(f"Reddit total: {len(all_deals)} fresh deals")
    return all_deals


X_SEARCH_QUERIES = [
    "food deal OR promo OR coupon OR BOGO OR discount",
    "UberEats promo code OR coupon OR free delivery",
    "DoorDash promo code OR coupon OR deal",
    "GrubHub promo code OR coupon OR deal",
    "restaurant deal OR coupon OR special OR BOGO",
    "fast food deal OR free OR coupon OR app offer",
]


def _parse_cookies(cookies_str: str) -> list[dict]:
    """Parse cookie string into Playwright cookie format."""
    cookies = []
    for pair in cookies_str.split(";"):
        pair = pair.strip()
        if "=" in pair:
            k, v = pair.split("=", 1)
            cookies.append({"name": k.strip(), "value": v.strip(), "domain": ".x.com", "path": "/"})
    return cookies


def _scrape_x_search(query: str, cookies: list[dict], timeout_ms: int = 30000) -> list[dict]:
    """Use Playwright to search X and intercept the API response."""
    from playwright.sync_api import sync_playwright

    tweets = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        )
        context.add_cookies(cookies)

        page = context.new_page()

        encoded_query = requests.utils.quote(query)
        url = f"https://x.com/search?q={encoded_query}&src=typed_query&f=live"

        # Navigate and wait for the SearchTimeline API response
        try:
            with page.expect_response(
                lambda r: "SearchTimeline" in r.url and r.status == 200,
                timeout=timeout_ms,
            ) as response_info:
                page.goto(url, timeout=timeout_ms)

            api_data = response_info.value.json()
        except Exception as e:
            logger.warning(f"X: no SearchTimeline response for '{query[:30]}' — {e}")
            browser.close()
            return []

        browser.close()

    # Parse the API response
    try:
        instructions = api_data["data"]["search_by_raw_query"]["search_timeline"]["timeline"]["instructions"]
        for instruction in instructions:
            for entry in instruction.get("entries", []):
                try:
                    result = entry["content"]["itemContent"]["tweet_results"]["result"]
                    if "tweet" in result:
                        result = result["tweet"]
                    legacy = result.get("legacy", {})
                    user_result = result.get("core", {}).get("user_results", {}).get("result", {})
                    user_core = user_result.get("core", {})

                    tweet_id = legacy.get("id_str", result.get("rest_id", ""))
                    text = legacy.get("full_text", "")
                    screen_name = user_core.get("screen_name", user_result.get("legacy", {}).get("screen_name", "unknown"))
                    created_str = legacy.get("created_at", "")

                    if not text or not tweet_id:
                        continue

                    created_dt = datetime.strptime(created_str, "%a %b %d %H:%M:%S %z %Y")
                    created_utc = created_dt.timestamp()

                    tweets.append({
                        "id": tweet_id,
                        "text": text,
                        "screen_name": screen_name,
                        "created_utc": created_utc,
                        "url": f"https://x.com/{screen_name}/status/{tweet_id}",
                    })
                except (KeyError, TypeError):
                    continue
    except (KeyError, TypeError):
        pass

    return tweets


def fetch_x_deals(limit_per_query: int = 20) -> list[dict]:
    """Fetch deals from X using Playwright to drive a real browser."""
    cookies_str = os.getenv("X_COOKIES", "")
    if not cookies_str:
        logger.error("X_COOKIES missing from .env")
        return []

    cookies = _parse_cookies(cookies_str)
    all_deals = []
    cutoff = time.time() - (MAX_AGE_HOURS * 3600)

    for query in X_SEARCH_QUERIES:
        try:
            tweets = _scrape_x_search(query, cookies)
            fresh = 0
            for tweet in tweets:
                if tweet["created_utc"] < cutoff:
                    continue
                fresh += 1
                age_hours = (time.time() - tweet["created_utc"]) / 3600
                all_deals.append({
                    "id": tweet["id"],
                    "title": tweet["text"][:200],
                    "body": tweet["text"],
                    "url": tweet["url"],
                    "source": "twitter",
                    "subreddit": "",
                    "created_utc": tweet["created_utc"],
                    "age_hours": round(age_hours, 1),
                })

            logger.info(f"X query '{query[:40]}...': {fresh}/{len(tweets)} within {MAX_AGE_HOURS}h")

        except Exception as e:
            logger.error(f"X query '{query[:40]}...': failed — {e}")
            continue

    logger.info(f"X total: {len(all_deals)} fresh deals")
    return all_deals


def fetch_all_deals() -> list[dict]:
    """Fetch from all sources. X is primary, Reddit is fallback."""
    x_deals = fetch_x_deals()
    reddit_deals = fetch_reddit_deals()
    all_deals = x_deals + reddit_deals
    logger.info(f"All sources: {len(all_deals)} total ({len(x_deals)} X + {len(reddit_deals)} Reddit)")
    return all_deals


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=== Testing X scraper (primary) ===\n")
    x_deals = fetch_x_deals(limit_per_query=5)
    print(f"Fetched {len(x_deals)} deals from X\n")
    for deal in x_deals[:5]:
        print(f"[X] ({deal['age_hours']}h ago) {deal['title'][:100]}")
        print(f"  URL: {deal['url']}")
        print()

    print("=== Testing Reddit scraper (fallback) ===\n")
    reddit_deals = fetch_reddit_deals(limit_per_sub=5)
    print(f"Fetched {len(reddit_deals)} deals from Reddit\n")
    for deal in reddit_deals[:5]:
        print(f"[r/{deal['subreddit']}] ({deal['age_hours']}h ago) {deal['title']}")
        print(f"  URL: {deal['url']}")
        print()

    print(f"=== Combined: {len(x_deals) + len(reddit_deals)} deals ===")
