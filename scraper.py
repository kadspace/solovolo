"""
Volo Sports San Diego - Pickup/Drop-in Scraper
Fetches volleyball and soccer pickups/drop-ins from Volo Sports GraphQL API
"""

import httpx
from datetime import datetime, timezone
from typing import Optional

API_URL = "https://volosports.com/hapi/v1/graphql"

HEADERS = {
    "content-type": "application/json",
    "origin": "https://www.volosports.com",
    "referer": "https://www.volosports.com/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

DISCOVER_DAILY_QUERY = """
query DiscoverDaily($where: discover_daily_bool_exp!, $limit: Int = 100, $offset: Int = 0) {
  discover_daily(
    where: $where
    order_by: [{event_start_date: asc}, {event_start_time_str: asc}, {event_end_time_str: asc}, {_id: asc}]
    limit: $limit
    offset: $offset
  ) {
    _id
    game_id
    game {
      _id
      start_time
      end_time
      venueByVenue {
        _id
        shorthand_name
        formatted_address
        neighborhoodByNeighborhoodId {
          _id
          name
          __typename
        }
        __typename
      }
      drop_in_capacity {
        _id
        total_available_spots
        __typename
      }
      leagueByLeague {
        _id
        program_type
        sportBySport {
          _id
          name
          __typename
        }
        __typename
      }
      __typename
    }
    league_id
    league {
      ...LeagueDetails
      __typename
    }
    event_start_date
    event_start_time_str
    event_end_time_str
    __typename
  }
  discover_daily_aggregate(where: $where) {
    aggregate {
      count
      __typename
    }
    __typename
  }
}

fragment LeagueDetails on leagues {
  _id
  name
  display_name
  program_type
  start_date
  is_premier
  is_volo_pass_exclusive
  start_time_estimate
  end_time_estimate
  banner_text
  header
  num_weeks_estimate
  num_playoff_weeks_estimate
  sportBySport {
    _id
    name
    __typename
  }
  registrants_aggregate {
    aggregate {
      count
      __typename
    }
    __typename
  }
  registrationByRegistration {
    _id
    max_registration_size
    min_registration_size
    available_spots
    __typename
  }
  neighborhoodByNeighborhood {
    _id
    name
    __typename
  }
  venueByVenue {
    _id
    shorthand_name
    formatted_address
    __typename
  }
  organizationByOrganization {
    _id
    is_volo_pass_active
    __typename
  }
  __typename
}
"""


def build_variables(
    organization: str = "San Diego",
    sports: Optional[list[str]] = None,
    program_types: Optional[list[str]] = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """Build GraphQL variables for the DiscoverDaily query."""
    now = datetime.now(timezone.utc).isoformat()

    if program_types is None:
        program_types = ["PICKUP", "PRACTICE", "CLINIC", "DROPIN"]

    # Base league filter
    league_filter = {
        "organizationByOrganization": {"name": {"_eq": organization}},
        "start_date": {"_gte": now},
        "program_type": {"_in": program_types},
        "status": {"_eq": "registration_open"},
        "registrationByRegistration": {
            "available_spots": {"_gte": 1},
            "registration_close_date": {"_gte": "now()"},
        },
    }

    # Add sport filter if specified
    if sports:
        league_filter["sportBySport"] = {"name": {"_in": sports}}

    # Base game filter (for drop-ins)
    game_filter = {
        "start_time": {"_gte": now},
        "drop_in_capacity": {},
        "leagueByLeague": {
            "organizationByOrganization": {"name": {"_eq": organization}},
        },
    }

    if sports:
        game_filter["leagueByLeague"]["sportBySport"] = {"name": {"_in": sports}}

    return {
        "limit": limit,
        "offset": offset,
        "where": {
            "_or": [
                {
                    "league_id": {"_is_null": False},
                    "league": league_filter,
                },
                {
                    "game_id": {"_is_null": False},
                    "game": game_filter,
                },
            ]
        },
    }


def fetch_activities(
    sports: Optional[list[str]] = None,
    organization: str = "San Diego",
) -> list[dict]:
    """Fetch all pickup/drop-in activities from Volo Sports."""
    variables = build_variables(organization=organization, sports=sports)

    payload = {
        "operationName": "DiscoverDaily",
        "variables": variables,
        "query": DISCOVER_DAILY_QUERY,
    }

    with httpx.Client(timeout=30.0) as client:
        response = client.post(API_URL, headers=HEADERS, json=payload)
        response.raise_for_status()
        data = response.json()

    if "errors" in data:
        raise Exception(f"GraphQL errors: {data['errors']}")

    activities = data.get("data", {}).get("discover_daily", [])
    total_count = (
        data.get("data", {})
        .get("discover_daily_aggregate", {})
        .get("aggregate", {})
        .get("count", 0)
    )

    print(f"Found {len(activities)} activities (total: {total_count})")
    return activities


def format_time(time_str: str) -> str:
    """Format a time string for display."""
    if not time_str:
        return "?"
    # If it's already in HH:MM format, return as-is
    if len(time_str) <= 5 and ":" in time_str:
        return time_str
    # If it's an ISO datetime, extract just the time
    try:
        dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        return dt.strftime("%I:%M %p").lstrip("0")
    except (ValueError, AttributeError):
        return time_str


def format_date(date_str: str) -> str:
    """Format a date string for display."""
    if not date_str:
        return "?"
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%a %b %d")  # e.g., "Thu Jan 30"
    except (ValueError, AttributeError):
        return date_str


def parse_activity(activity: dict) -> dict:
    """Parse a raw activity into a cleaner format."""
    result = {
        "id": activity["_id"],
        "league_id": activity.get("league_id"),
        "game_id": activity.get("game_id"),
        "type": None,
        "sport": None,
        "name": None,
        "date": activity.get("event_start_date"),
        "start_time": activity.get("event_start_time_str"),
        "end_time": activity.get("event_end_time_str"),
        "venue": None,
        "address": None,
        "neighborhood": None,
        "spots_available": None,
        "max_spots": None,
        "registrants": None,
        "url": None,
    }

    # Handle league-based activities (PICKUP, PRACTICE, CLINIC)
    if activity.get("league"):
        league = activity["league"]
        result["type"] = league.get("program_type")
        result["name"] = league.get("display_name") or league.get("name")
        result["sport"] = league.get("sportBySport", {}).get("name")
        result["url"] = f"https://www.volosports.com/l/{activity.get('league_id')}"

        if league.get("venueByVenue"):
            result["venue"] = league["venueByVenue"].get("shorthand_name")
            result["address"] = league["venueByVenue"].get("formatted_address")

        if league.get("neighborhoodByNeighborhood"):
            result["neighborhood"] = league["neighborhoodByNeighborhood"].get("name")

        if league.get("registrationByRegistration"):
            reg = league["registrationByRegistration"]
            result["spots_available"] = reg.get("available_spots")
            result["max_spots"] = reg.get("max_registration_size")

        if league.get("registrants_aggregate"):
            result["registrants"] = league["registrants_aggregate"]["aggregate"]["count"]

    # Handle game-based activities (drop-ins for existing league games)
    elif activity.get("game"):
        game = activity["game"]
        result["type"] = "DROP-IN"
        result["url"] = f"https://www.volosports.com/d/{activity.get('game_id')}"

        if game.get("leagueByLeague"):
            league = game["leagueByLeague"]
            result["sport"] = league.get("sportBySport", {}).get("name")
            # Build a descriptive name for drop-in games
            sport_name = result["sport"] or "Activity"
            result["name"] = f"{sport_name} Drop-In Game"

        if game.get("venueByVenue"):
            venue = game["venueByVenue"]
            result["venue"] = venue.get("shorthand_name")
            result["address"] = venue.get("formatted_address")
            if venue.get("neighborhoodByNeighborhoodId"):
                result["neighborhood"] = venue["neighborhoodByNeighborhoodId"].get("name")

        if game.get("drop_in_capacity"):
            result["spots_available"] = game["drop_in_capacity"].get("total_available_spots")

        # Use game times if available (they're in ISO format)
        if game.get("start_time"):
            result["start_time"] = game["start_time"]
        if game.get("end_time"):
            result["end_time"] = game["end_time"]

    return result


def print_activity(activity: dict) -> None:
    """Pretty print an activity."""
    spots = activity.get("spots_available")
    spots_str = f"{spots} spots" if spots is not None else "? spots"

    date_str = format_date(activity["date"])
    start_str = format_time(activity["start_time"])
    end_str = format_time(activity["end_time"])

    print(f"\n{'='*60}")
    print(f"[{activity['type']}] {activity['sport']}: {activity['name']}")
    print(f"  When: {date_str} @ {start_str} - {end_str}")
    print(f"  Where: {activity['venue']}", end="")
    if activity['neighborhood']:
        print(f" ({activity['neighborhood']})")
    else:
        print()
    print(f"  Spots: {spots_str}")
    if activity.get("url"):
        print(f"  Link: {activity['url']}")


def main():
    """Main entry point."""
    print("Fetching San Diego Volleyball & Soccer pickups/drop-ins...")
    print("-" * 60)

    # Fetch volleyball and soccer only
    activities = fetch_activities(sports=["Volleyball", "Soccer"])

    if not activities:
        print("No activities found!")
        return

    # Parse and display
    parsed = [parse_activity(a) for a in activities]

    # Group by sport
    volleyball = [a for a in parsed if a["sport"] == "Volleyball"]
    soccer = [a for a in parsed if a["sport"] == "Soccer"]

    print(f"\n{'#'*60}")
    print(f"# VOLLEYBALL ({len(volleyball)} activities)")
    print(f"{'#'*60}")
    for activity in volleyball:
        print_activity(activity)

    print(f"\n{'#'*60}")
    print(f"# SOCCER ({len(soccer)} activities)")
    print(f"{'#'*60}")
    for activity in soccer:
        print_activity(activity)

    print(f"\n{'='*60}")
    print(f"Total: {len(volleyball)} volleyball, {len(soccer)} soccer")


if __name__ == "__main__":
    main()
