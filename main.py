import logging
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv

load_dotenv()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Quiet down noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    interval = int(os.getenv("POLL_INTERVAL_MINUTES", "30"))
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")

    print(f"=== Adrian Deal Bot ===")
    print(f"Polling every {interval} minutes")
    print(f"Chatbot enabled")
    print(f"Press Ctrl+C to stop\n")

    # Start the deal pipeline scheduler in a background thread
    from scheduler import start as start_scheduler
    scheduler = start_scheduler(interval_minutes=interval)

    # Build and run the Telegram bot listener on the main thread
    from telegram.ext import Application, MessageHandler, filters
    from agents.chatbot import handle_message

    app = Application.builder().token(bot_token).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    try:
        app.run_polling(drop_pending_updates=True)
    finally:
        scheduler.shutdown(wait=False)
        logging.getLogger(__name__).info("Scheduler stopped.")


if __name__ == "__main__":
    main()
