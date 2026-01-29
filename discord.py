"""
Discord webhook integration for Volo Sports notifications.
"""

import httpx
from typing import Optional


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

    # Sport emoji
    sport_emoji = {
        "Volleyball": "\U0001F3D0",
        "Soccer": "\u26BD",
    }.get(activity.get("sport"), "\U0001F3C3")

    title = f"{sport_emoji} {activity.get('name', 'Activity')}"

    # Build description
    spots = activity.get("spots_available")
    spots_str = f"{spots} spots available" if spots is not None else "Spots unknown"

    description = f"**{activity.get('type', 'ACTIVITY')}** - {spots_str}"

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

    # Group by sport
    volleyball = [a for a in activities if a.get("sport") == "Volleyball"]
    soccer = [a for a in activities if a.get("sport") == "Soccer"]

    embeds = []

    # Add volleyball activities
    for activity in volleyball[:5]:  # Discord limit: 10 embeds per message
        embeds.append(build_activity_embed(activity))

    # Add soccer activities
    for activity in soccer[:5]:
        embeds.append(build_activity_embed(activity))

    if not embeds:
        return True

    # Build summary message
    summary = f"**{len(activities)} new activities found!**"
    if volleyball:
        summary += f"\n\U0001F3D0 {len(volleyball)} Volleyball"
    if soccer:
        summary += f"\n\u26BD {len(soccer)} Soccer"

    return send_discord_message(
        webhook_url=webhook_url,
        content=summary,
        embeds=embeds[:10],  # Discord max 10 embeds
    )
