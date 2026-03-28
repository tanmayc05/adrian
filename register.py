import re
import sys
from db.database import add_subscriber, get_all_subscribers

CATEGORIES = ["food", "electronics", "clothing", "travel", "gaming", "general"]


def validate_phone(phone: str) -> bool:
    """Validate E.164 format: + followed by 10-15 digits."""
    return bool(re.match(r"^\+[1-9]\d{9,14}$", phone))


def run():
    print("=== Adrian — Subscriber Registration ===\n")

    # Phone number
    while True:
        phone = input("Phone number (E.164 format, e.g. +11234567890): ").strip()
        if validate_phone(phone):
            break
        print("  Invalid format. Must start with + followed by 10-15 digits.\n")

    # Category selection
    print("\nSelect deal categories (comma-separated numbers):\n")
    for i, cat in enumerate(CATEGORIES, 1):
        print(f"  {i}. {cat}")

    while True:
        choices = input("\nYour picks (e.g. 1,3,5): ").strip()
        try:
            indices = [int(c.strip()) for c in choices.split(",")]
            selected = [CATEGORIES[i - 1] for i in indices if 1 <= i <= len(CATEGORIES)]
            if selected:
                break
        except (ValueError, IndexError):
            pass
        print("  Invalid selection. Enter numbers separated by commas.")

    # Save
    add_subscriber(phone, selected)
    print(f"\nRegistered {phone} for: {', '.join(selected)}")

    # Show all subscribers
    print("\n--- All subscribers ---")
    for s in get_all_subscribers():
        print(f"  {s['phone']} -> {', '.join(s['categories'])}")


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(0)
