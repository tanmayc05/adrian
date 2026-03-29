import os
import logging
import asyncio
import telegram
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def format_deal_message(deal: dict) -> str:
    """Format a deal into a clean Telegram message."""
    category = deal.get("llm_category", "deal").upper()
    title = deal.get("title", "").strip()
    url = deal.get("url", "")
    source = deal.get("source", "")
    age = deal.get("age_hours", 0)

    # Truncate title if too long
    if len(title) > 200:
        title = title[:197] + "..."

    age_str = f"{age}h ago" if age >= 1 else "just now"

    lines = [
        f"🔥 [{category}] {title}",
        f"🔗 {url}",
        f"📍 {source} • {age_str}",
    ]
    return "\n".join(lines)


async def _send_deal(deal: dict, chat_id: str = "") -> bool:
    """Send a single deal to a Telegram chat."""
    target = chat_id or CHAT_ID
    if not BOT_TOKEN or not target:
        logger.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing")
        return False

    bot = telegram.Bot(token=BOT_TOKEN)
    message = format_deal_message(deal)

    try:
        await bot.send_message(
            chat_id=target,
            text=message,
            disable_web_page_preview=False,
        )
        logger.info(f"Sent: {deal['title'][:50]}")
        return True
    except Exception as e:
        logger.error(f"Failed to send: {e}")
        return False


def send_deal(deal: dict, chat_id: str = "") -> bool:
    """Sync wrapper for sending a deal."""
    try:
        return asyncio.run(_send_deal(deal, chat_id))
    except Exception as e:
        logger.error(f"Notifier failed: {e}")
        return False


def send_deals(deals: list[dict], chat_id: str = "") -> int:
    """Send multiple deals. Returns count of successfully sent."""

    async def _send_all():
        target = chat_id or CHAT_ID
        if not BOT_TOKEN or not target:
            logger.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing")
            return 0

        bot = telegram.Bot(token=BOT_TOKEN)
        sent = 0
        for i, deal in enumerate(deals):
            # Telegram rate limit: ~30 msgs/min per group — 2s gap is safe
            if i > 0:
                await asyncio.sleep(2)

            message = format_deal_message(deal)
            try:
                await bot.send_message(
                    chat_id=target,
                    text=message,
                    disable_web_page_preview=False,
                )
                sent += 1
                logger.info(f"Sent: {deal['title'][:50]}")
            except Exception as e:
                logger.error(f"Failed to send: {e}")
        return sent

    try:
        return asyncio.run(_send_all())
    except Exception as e:
        logger.error(f"Notifier failed: {e}")
        return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    test_deal = {
        "id": "test123",
        "title": "BOGO Big Macs at McDonald's — app deal, today only!",
        "body": "Open your McDonald's app for a free Big Mac with any purchase.",
        "url": "https://mcdonalds.com/deals",
        "source": "twitter",
        "subreddit": "",
        "age_hours": 0.5,
        "llm_category": "food",
        "llm_confidence": 0.9,
    }

    print("Sending test deal to Telegram...\n")
    print(format_deal_message(test_deal))
    print()
    success = send_deal(test_deal)
    print(f"\n{'Sent!' if success else 'Failed.'}")
