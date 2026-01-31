"""
Volo Sports Watcher - Monitors for new pickups/drop-ins and sends Discord notifications.
"""

import sqlite3
import time
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from scraper import fetch_activities, parse_activity, format_date, format_time
from discord import notify_new_activities


def should_notify(activity: dict) -> bool:
    """Check if we should notify for this activity.

    - PICKUP activities: always notify (anyone can join)
    - DROP-IN activities: only notify if there are male-eligible spots
    """
    activity_type = (activity.get("type") or "").upper()

    # Pickups are open to everyone
    if activity_type == "PICKUP":
        return True

    # For drop-ins, only notify if there are spots men can apply for
    if activity_type in ("DROP-IN", "DROPIN"):
        male_eligible = activity.get("male_eligible_spots")
        # If we have the data, only notify if there are male-eligible spots
        if male_eligible is not None:
            return male_eligible > 0
        # Fallback: if data missing, notify anyway (shouldn't happen)
        return True

    # Default: notify for everything else (PRACTICE, CLINIC, etc.)
    return True

# Configuration
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", 300))  # 5 minutes default
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
DB_PATH = Path(__file__).parent / "volo.db"


def init_db(db_path: Path) -> sqlite3.Connection:
    """Initialize SQLite database for tracking seen activities."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_activities (
            id TEXT PRIMARY KEY,
            sport TEXT,
            name TEXT,
            date TEXT,
            venue TEXT,
            spots_available INTEGER,
            first_seen_at TEXT,
            last_seen_at TEXT,
            notified INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id TEXT,
            event_type TEXT,
            details TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    return conn


def get_seen_ids(conn: sqlite3.Connection) -> set[str]:
    """Get all previously seen activity IDs."""
    cursor = conn.execute("SELECT id FROM seen_activities")
    return {row[0] for row in cursor.fetchall()}


def save_activity(conn: sqlite3.Connection, activity: dict, is_new: bool = True) -> None:
    """Save an activity to the database."""
    now = datetime.now(timezone.utc).isoformat()

    if is_new:
        conn.execute("""
            INSERT OR REPLACE INTO seen_activities
            (id, sport, name, date, venue, spots_available, first_seen_at, last_seen_at, notified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            activity["id"],
            activity.get("sport"),
            activity.get("name"),
            activity.get("date"),
            activity.get("venue"),
            activity.get("spots_available"),
            now,
            now,
        ))

        conn.execute("""
            INSERT INTO activity_log (activity_id, event_type, details, created_at)
            VALUES (?, 'NEW', ?, ?)
        """, (activity["id"], f"{activity.get('sport')}: {activity.get('name')}", now))
    else:
        conn.execute("""
            UPDATE seen_activities
            SET spots_available = ?, last_seen_at = ?
            WHERE id = ?
        """, (activity.get("spots_available"), now, activity["id"]))

    conn.commit()


def mark_notified(conn: sqlite3.Connection, activity_ids: list[str]) -> None:
    """Mark activities as notified."""
    for aid in activity_ids:
        conn.execute("UPDATE seen_activities SET notified = 1 WHERE id = ?", (aid,))
    conn.commit()


def check_for_new_activities(conn: sqlite3.Connection) -> list[dict]:
    """Fetch activities and identify new ones."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Checking for new activities...")

    try:
        raw_activities = fetch_activities(sports=["Volleyball", "Soccer"])
    except Exception as e:
        print(f"Error fetching activities: {e}")
        return []

    seen_ids = get_seen_ids(conn)
    new_activities = []

    for raw in raw_activities:
        activity = parse_activity(raw)

        # Format for display/storage
        activity["date"] = format_date(activity["date"])
        activity["start_time"] = format_time(activity["start_time"])
        activity["end_time"] = format_time(activity["end_time"])

        if activity["id"] not in seen_ids:
            new_activities.append(activity)
            save_activity(conn, activity, is_new=True)
            print(f"  NEW: [{activity['type']}] {activity['sport']}: {activity['name']}")
            print(f"       {activity['date']} @ {activity['start_time']} - {activity['venue']}")
        else:
            save_activity(conn, activity, is_new=False)

    return new_activities


def run_watcher():
    """Main watcher loop."""
    print("=" * 60)
    print("Volo Sports Watcher")
    print("=" * 60)
    print(f"Poll interval: {POLL_INTERVAL} seconds")
    print(f"Discord webhook: {'configured' if DISCORD_WEBHOOK_URL else 'NOT CONFIGURED'}")
    print(f"Database: {DB_PATH}")
    print("=" * 60)

    if not DISCORD_WEBHOOK_URL:
        print("\nWARNING: No Discord webhook URL configured!")
        print("Set DISCORD_WEBHOOK_URL environment variable to enable notifications.\n")

    conn = init_db(DB_PATH)

    # Initial fetch to populate database
    print("\nInitial fetch...")
    new_activities = check_for_new_activities(conn)

    if new_activities:
        print(f"\nFound {len(new_activities)} activities on first run.")
        if DISCORD_WEBHOOK_URL:
            print("Skipping notifications for initial batch (assuming these are existing).")
        # Mark all as notified to avoid spam on first run
        mark_notified(conn, [a["id"] for a in new_activities])
    else:
        print("No activities found.")

    print(f"\nWatching for new activities (checking every {POLL_INTERVAL}s)...")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(POLL_INTERVAL)

            new_activities = check_for_new_activities(conn)

            if new_activities:
                print(f"\n>>> {len(new_activities)} NEW ACTIVITIES FOUND! <<<\n")

                # Filter to only activities where men can join
                notifiable = [a for a in new_activities if should_notify(a)]
                skipped = len(new_activities) - len(notifiable)
                if skipped:
                    print(f"  (Skipped {skipped} drop-ins with no male-eligible spots)")

                if DISCORD_WEBHOOK_URL and notifiable:
                    success = notify_new_activities(DISCORD_WEBHOOK_URL, notifiable)
                    if success:
                        mark_notified(conn, [a["id"] for a in new_activities])
                        print("Discord notification sent!")
                    else:
                        print("Failed to send Discord notification.")
                elif not notifiable:
                    mark_notified(conn, [a["id"] for a in new_activities])
                    print("  No notifiable activities (none had male-eligible spots).")
            else:
                print("  No new activities.")

    except KeyboardInterrupt:
        print("\n\nStopping watcher...")
    finally:
        conn.close()


if __name__ == "__main__":
    run_watcher()
