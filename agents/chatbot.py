import os
import json
import time
import logging
from anthropic import AsyncAnthropic
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from db.database import search_deals, get_recent_deals

logger = logging.getLogger(__name__)

client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "").lower()  # e.g. "adrianbot"

# Per-user cooldown tracking: {user_id: last_response_timestamp}
_cooldowns: dict[int, float] = {}
COOLDOWN_SECONDS = 10

SYSTEM_PROMPT = """You are Adrian, a friendly food deal assistant in a Telegram group chat.
Your job is to understand what the user wants and respond with a JSON intent.

Possible intents:
1. "search_deals" — user is looking for deals matching specific keywords (e.g. "any chipotle deals?", "doordash promos?")
   → {"intent": "search_deals", "keywords": ["chipotle"], "hours": 24}
2. "recent_deals" — user wants to see recent/today's deals (e.g. "what did I miss?", "any deals today?")
   → {"intent": "recent_deals", "hours": 24}
3. "help" — user asks what you can do (e.g. "what can you do?", "help")
   → {"intent": "help"}
4. "greeting" — user says hi/hello
   → {"intent": "greeting"}
5. "off_topic" — anything not about deals
   → {"intent": "off_topic"}

Rules:
- For "search_deals", extract meaningful keywords (brand names, food types). Strip filler words.
- If the user says "today" or "recent", use hours=24. If they say "this week", use hours=168.
- Default hours to 24 if not specified.
- Respond with ONLY valid JSON, no other text."""


def _is_triggered(update: Update) -> bool:
    """Check if the bot should respond to this message."""
    message = update.message
    if not message or not message.text:
        return False

    # 1. Direct reply to one of the bot's messages
    if message.reply_to_message and message.reply_to_message.from_user:
        if message.reply_to_message.from_user.is_bot:
            bot_user = message.reply_to_message.from_user.username or ""
            if BOT_USERNAME and bot_user.lower() == BOT_USERNAME:
                return True

    # 2. @mention of the bot
    text = message.text.lower()
    if BOT_USERNAME and f"@{BOT_USERNAME}" in text:
        return True

    # 3. "adrian" keyword
    if "adrian" in text:
        return True

    return False


def _format_deals_response(deals: list[dict], query_desc: str) -> str:
    """Format a list of deals into a readable Telegram message."""
    if not deals:
        return f"No deals found for {query_desc}. I'll keep an eye out!"

    lines = [f"Here's what I found ({len(deals)} deal{'s' if len(deals) != 1 else ''}):\n"]
    for d in deals[:10]:
        title = d.get("title", "")[:150]
        url = d.get("url", "")
        source = d.get("source", "")
        lines.append(f"• {title}")
        if url:
            lines.append(f"  {url}")
        if source:
            lines.append(f"  via {source}")
        lines.append("")

    return "\n".join(lines).strip()


async def get_response(user_message: str) -> str:
    """Parse user intent with Claude Haiku, query DB, and build a reply."""
    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        text = response.content[0].text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0].strip()
        result = json.loads(text)
    except Exception as e:
        logger.error(f"Haiku parse error: {e}")
        return "Sorry, I had trouble understanding that. Try asking about deals — like 'any chipotle deals today?'"

    intent = result.get("intent", "off_topic")

    if intent == "search_deals":
        keywords = result.get("keywords", [])
        hours = result.get("hours", 24)
        if not keywords:
            return "What kind of deals are you looking for? Try something like 'any McDonald's deals?'"
        deals = search_deals(keywords, hours)
        return _format_deals_response(deals, ", ".join(keywords))

    elif intent == "recent_deals":
        hours = result.get("hours", 24)
        deals = get_recent_deals(hours)
        label = "today" if hours <= 24 else f"the last {hours} hours"
        return _format_deals_response(deals, label)

    elif intent == "help":
        return (
            "I'm Adrian, your deal-finding buddy! Here's what I can do:\n\n"
            "• Ask me about specific deals: \"any Chipotle deals?\"\n"
            "• See what's new: \"what did I miss today?\"\n"
            "• Search by type: \"any BOGO deals?\"\n\n"
            "Just mention my name, @mention me, or reply to one of my messages!"
        )

    elif intent == "greeting":
        return "Hey! I'm Adrian — ask me about food deals anytime. Try 'any deals today?'"

    else:
        return "I'm all about food deals! Try asking something like 'any DoorDash promos?' or 'what did I miss today?'"


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Telegram message handler — only responds when triggered."""
    if not _is_triggered(update):
        return

    user_id = update.effective_user.id if update.effective_user else 0

    # Per-user cooldown
    now = time.time()
    if now - _cooldowns.get(user_id, 0) < COOLDOWN_SECONDS:
        return
    _cooldowns[user_id] = now

    # Show typing indicator
    await update.message.chat.send_action(ChatAction.TYPING)

    # Strip trigger text to get the actual question
    text = update.message.text
    if BOT_USERNAME:
        text = text.replace(f"@{BOT_USERNAME}", "").replace(f"@{BOT_USERNAME.upper()}", "")
    text = text.strip()

    reply = await get_response(text)
    await update.message.reply_text(reply)
