import os
import json
import time
import logging
from anthropic import Anthropic, RateLimitError
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You are a strict filter for a FOOD deal alert bot. You decide if a post contains a real, currently active food/restaurant/delivery deal.

A deal MUST have at least one of these:
- A specific discount (% off, $ off, BOGO, free item)
- A promo code or coupon code
- A limited-time offer from a restaurant, fast food chain, or delivery app

REJECT these — they are NOT deals:
- Generic brand tweets ("Game day starts with Chipotle" = marketing, not a deal)
- Complaints, questions, rants, or discussions about food
- Expired or future deals (must be active NOW)
- Crypto, betting, or non-food promos
- News articles or reviews about restaurants
- Someone just mentioning a brand without an actual offer

Examples:

PASS: "Use code SAVE50 on DoorDash for 50% off your next order — expires tonight!"
→ {"is_relevant": true, "category": "food", "confidence": 0.95, "reason": "Active DoorDash promo code with specific discount"}

PASS: "BOGO Big Macs at McDonald's today only, no code needed, just use the app"
→ {"is_relevant": true, "category": "food", "confidence": 0.9, "reason": "Active BOGO offer at McDonald's"}

REJECT: "Nothing beats a Chipotle bowl after a long day 🌯"
→ {"is_relevant": false, "category": "food", "confidence": 0.1, "reason": "Brand mention, not a deal"}

REJECT: "UberEats drivers are being exploited and underpaid"
→ {"is_relevant": false, "category": "food", "confidence": 0.05, "reason": "Complaint, not a deal"}

REJECT: "Does anyone know if the Wendy's 4 for $4 is still available?"
→ {"is_relevant": false, "category": "food", "confidence": 0.15, "reason": "Question about a deal, not confirmation of active deal"}

LOCATION RULES (only apply when subscriber locations are provided):
- REJECT deals that are clearly limited to a specific region or country that does NOT overlap with any subscriber location.
- Examples: a UK-only promo should be rejected if subscribers are all in the US; a deal at a regional chain that only exists in one area should be rejected if subscribers aren't there.
- If the deal's location is ambiguous or nationwide, do NOT reject it — give it the benefit of the doubt.
- If no subscriber locations are provided, skip location filtering entirely.

Respond with ONLY valid JSON, no other text:
{"is_relevant": true/false, "category": "food", "confidence": 0.0-1.0, "reason": "brief explanation"}"""


def filter_deals(deals: list[dict], categories: list[str], locations: list[str] | None = None) -> list[dict]:
    """Filter deals using Claude Haiku. Returns only relevant deals with LLM metadata."""
    if not deals:
        return []

    filtered = []

    for deal in deals:
        try:
            location_line = ""
            if locations:
                location_line = f"\nSubscriber locations: {', '.join(locations)}"

            user_prompt = f"""Deal:
Title: {deal['title'][:300]}
Body: {deal.get('body', '')[:500]}
Source: {deal['source']}

User's preferred categories: {', '.join(categories)}{location_line}

Is this a real, currently active deal that matches the user's preferences?"""

            # Retry up to 3 times on rate limit errors
            response = None
            for attempt in range(3):
                try:
                    response = client.messages.create(
                        model="claude-haiku-4-5-20251001",
                        max_tokens=150,
                        system=SYSTEM_PROMPT,
                        messages=[{"role": "user", "content": user_prompt}],
                    )
                    break
                except RateLimitError:
                    wait = 2 ** attempt  # 1s, 2s, 4s
                    logger.warning(f"Rate limited, retrying in {wait}s...")
                    time.sleep(wait)

            if response is None:
                logger.error(f"Rate limit exceeded after 3 retries — {deal['title'][:60]}")
                continue

            text = response.content[0].text.strip()
            # Strip markdown code fences if present
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                text = text.rsplit("```", 1)[0].strip()
            result = json.loads(text)

            if result.get("is_relevant") and result.get("confidence", 0) >= 0.6:
                deal["llm_category"] = result.get("category", "general")
                deal["llm_confidence"] = result.get("confidence", 0)
                deal["llm_reason"] = result.get("reason", "")
                filtered.append(deal)
                logger.info(f"PASS ({result['confidence']}) [{result.get('category')}] {deal['title'][:60]}")
            else:
                logger.debug(f"REJECT: {result.get('reason', 'no reason')} — {deal['title'][:60]}")

        except Exception as e:
            logger.error(f"LLM filter error: {e} — {deal['title'][:60]}")
            continue

    logger.info(f"Filter: {len(filtered)}/{len(deals)} deals passed")
    return filtered


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Mock deals to test
    mock_deals = [
        {
            "id": "1",
            "title": "DoorDash: 50% off your next order with code SAVE50, expires tonight!",
            "body": "Use code SAVE50 at checkout. Max $15 discount. Valid today only.",
            "url": "https://example.com/1",
            "source": "twitter",
            "subreddit": "",
            "created_utc": 0,
            "age_hours": 1.0,
        },
        {
            "id": "2",
            "title": "This crap pisses me the hell off",
            "body": "UberEats charged me extra fees again smh",
            "url": "https://example.com/2",
            "source": "reddit",
            "subreddit": "UberEATS",
            "created_utc": 0,
            "age_hours": 2.0,
        },
        {
            "id": "3",
            "title": "Free Chick-fil-A sandwich with any purchase through the app this week",
            "body": "Just saw this in my Chick-fil-A app. Free original chicken sandwich with any purchase.",
            "url": "https://example.com/3",
            "source": "reddit",
            "subreddit": "fastfood",
            "created_utc": 0,
            "age_hours": 5.0,
        },
        {
            "id": "4",
            "title": "Does anybody know if GrubHub still does the $5 off promo?",
            "body": "I used to get $5 off coupons all the time but haven't seen one in months",
            "url": "https://example.com/4",
            "source": "reddit",
            "subreddit": "GrubHub",
            "created_utc": 0,
            "age_hours": 3.0,
        },
        {
            "id": "5",
            "title": "BOGO Big Macs at McDonald's today only — app deal",
            "body": "Open your McDonald's app, BOGO Big Mac deal is live right now. No code needed.",
            "url": "https://example.com/5",
            "source": "twitter",
            "subreddit": "",
            "created_utc": 0,
            "age_hours": 0.5,
        },
    ]

    categories = ["food", "general"]

    print("=== Testing LLM Filter ===\n")
    results = filter_deals(mock_deals, categories)
    print(f"\n--- {len(results)} deals passed filter ---\n")
    for d in results:
        print(f"[{d['llm_category']}] ({d['llm_confidence']}) {d['title']}")
        print(f"  Reason: {d['llm_reason']}")
        print()
