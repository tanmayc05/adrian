import requests
import logging
import time

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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    deals = fetch_reddit_deals(limit_per_sub=5)
    print(f"\n--- Fetched {len(deals)} deals from Reddit ---\n")
    for deal in deals:
        print(f"[r/{deal['subreddit']}] ({deal['age_hours']}h ago) {deal['title']}")
        print(f"  URL: {deal['url']}")
        print()
