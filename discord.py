"""
Discord webhook integration for Volo Sports notifications.
"""

import httpx
from collections import Counter
from typing import Optional


SPORT_EMOJI = {
    "Basketball": "\U0001F3C0",
    "Bowling": "\U0001F3B3",
    "Cornhole": "\U0001F3AF",
    "Dodgeball": "\U0001F3D0",
    "Flag Football": "\U0001F3C8",
    "Kickball": "\u26BD",
    "Pickleball": "\U0001F3BE",
    "Soccer": "\u26BD",
    "Tennis": "\U0001F3BE",
    "Volleyball": "\U0001F3D0",
}


def sport_emoji(sport: Optional[str]) -> str:
    """Return a readable emoji for a sport name."""
    return SPORT_EMOJI.get(sport or "", "\U0001F3C3")


def send_discord_message(
    webhook_url: str,
    content: Optional[str] = None,
    embeds: Optional[list[dict]] = None,
    username: str = "Volo Sports Bot",
) -> bool:
    """Send a message to Discord via webhook."""
    if not webhook_url:
        print("No Discord webhook URL configured")
        return False

    payload = {"username": username}

    if content:
        payload["content"] = content
    if embeds:
        payload["embeds"] = embeds

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(webhook_url, json=payload)
            response.raise_for_status()
            return True
    except httpx.HTTPError as e:
        print(f"Discord webhook error: {e}")
        return False


def build_activity_embed(activity: dict, is_new: bool = True) -> dict:
    """Build a Discord embed for an activity."""
    # Color: green for new, blue for update
    color = 0x00FF00 if is_new else 0x0099FF

    title = f"{sport_emoji(activity.get('sport'))} {activity.get('name', 'Activity')}"

    # Build description
    spots = activity.get("spots_available")
    spots_str = f"{spots} spots available" if spots is not None else "Spots unknown"

    description = f"**{activity.get('type', 'ACTIVITY')}** - {spots_str}"
    male_eligible = activity.get("male_eligible_spots")
    if male_eligible is not None:
        description += f" ({male_eligible} male-eligible)"

    fields = [
        {
            "name": "\U0001F4C5 When",
            "value": f"{activity.get('date', '?')} @ {activity.get('start_time', '?')} - {activity.get('end_time', '?')}",
            "inline": True,
        },
        {
            "name": "\U0001F4CD Where",
            "value": f"{activity.get('venue', '?')}\n{activity.get('neighborhood', '')}",
            "inline": True,
        },
    ]

    embed = {
        "title": title,
        "description": description,
        "color": color,
        "fields": fields,
    }

    if activity.get("url"):
        embed["url"] = activity["url"]

    return embed


def notify_new_activities(webhook_url: str, activities: list[dict]) -> bool:
    """Send Discord notification for new activities."""
    if not activities:
        return True

    # Discord limit: 10 embeds per message.
    embeds = [build_activity_embed(activity) for activity in activities[:10]]

    # Build summary message
    summary = f"**{len(activities)} new activities found!**"
    sport_counts = Counter(a.get("sport") or "Other" for a in activities)
    for sport, count in sorted(sport_counts.items()):
        summary += f"\n{sport_emoji(sport)} {count} {sport}"
    if len(activities) > len(embeds):
        summary += f"\nShowing first {len(embeds)} details."

    return send_discord_message(
        webhook_url=webhook_url,
        content=summary,
        embeds=embeds[:10],  # Discord max 10 embeds
    )
