import logging
import sys
import os
from typing import TypedDict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from langgraph.graph import StateGraph, START, END

from agents.scraper import fetch_all_deals
from agents.filter_agent import filter_deals
from agents.notifier import send_deals
from db.database import get_all_subscribers, has_seen_deal, mark_deal_seen, save_deal

logger = logging.getLogger(__name__)


class PipelineState(TypedDict):
    raw_deals: list[dict]
    new_deals: list[dict]
    filtered_deals: list[dict]  # deals that passed LLM filter
    sent_count: int


def scrape_node(state: PipelineState) -> dict:
    """Scrape deals from all sources."""
    logger.info("=== SCRAPE ===")
    raw_deals = fetch_all_deals()
    logger.info(f"Scraped {len(raw_deals)} raw deals")
    return {"raw_deals": raw_deals}


def dedup_node(state: PipelineState) -> dict:
    """Remove deals we've already seen."""
    logger.info("=== DEDUP ===")
    new_deals = []
    for deal in state["raw_deals"]:
        if not has_seen_deal(deal["id"], deal["source"]):
            new_deals.append(deal)
    logger.info(f"Dedup: {len(new_deals)} new / {len(state['raw_deals'])} total")
    return {"new_deals": new_deals}


def filter_node(state: PipelineState) -> dict:
    """Filter deals once using LLM. Uses the union of all subscriber categories."""
    logger.info("=== FILTER ===")
    subscribers = get_all_subscribers()
    if not subscribers:
        logger.warning("No subscribers registered")
        return {"filtered_deals": []}

    # Collect all unique categories across all subscribers — filter once
    all_categories = set()
    all_locations = set()
    for sub in subscribers:
        all_categories.update(sub["categories"])
        loc = sub.get("location", "").strip()
        if loc:
            all_locations.add(loc)

    filtered = filter_deals(state["new_deals"], list(all_categories), list(all_locations) or None)
    logger.info(f"Filter: {len(filtered)}/{len(state['new_deals'])} deals passed")
    return {"filtered_deals": filtered}


def notify_node(state: PipelineState) -> dict:
    """Send filtered deals via Telegram and mark as seen."""
    logger.info("=== NOTIFY ===")
    deals = state["filtered_deals"]

    if not deals:
        logger.info("No deals to send")
        return {"sent_count": 0}

    sent = send_deals(deals)

    # Mark all deals as seen (even if send failed — avoid spam on retry)
    # Also persist to deals table for chatbot lookups
    for deal in deals:
        mark_deal_seen(deal["id"], deal["source"])
        save_deal(deal)

    logger.info(f"Sent {sent} deal alerts")
    return {"sent_count": sent}


def build_pipeline() -> StateGraph:
    """Build the LangGraph pipeline: scrape → dedup → filter_and_match → notify."""
    graph = StateGraph(PipelineState)

    graph.add_node("scrape", scrape_node)
    graph.add_node("dedup", dedup_node)
    graph.add_node("filter", filter_node)
    graph.add_node("notify", notify_node)

    graph.add_edge(START, "scrape")
    graph.add_edge("scrape", "dedup")
    graph.add_edge("dedup", "filter")
    graph.add_edge("filter", "notify")
    graph.add_edge("notify", END)

    return graph.compile()


def run_pipeline():
    """Run the full pipeline once."""
    pipeline = build_pipeline()
    result = pipeline.invoke({
        "raw_deals": [],
        "new_deals": [],
        "filtered_deals": [],
        "sent_count": 0,
    })
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=== Running Adrian Pipeline ===\n")
    result = run_pipeline()
    print(f"\n=== Done. Sent {result['sent_count']} alerts ===")
