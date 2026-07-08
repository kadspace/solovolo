const API_URL = "https://volosports.com/hapi/v1/graphql";
const PACIFIC_TZ = "America/Los_Angeles";

const HEADERS = {
  "content-type": "application/json",
  origin: "https://www.volosports.com",
  referer: "https://www.volosports.com/",
  "user-agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
};

const DISCOVER_DAILY_QUERY = `
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
        total_male_eligible_spots
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
`;

const SPORT_EMOJI = {
  Basketball: "\uD83C\uDFC0",
  Bowling: "\uD83C\uDFB3",
  Cornhole: "\uD83C\uDFAF",
  Dodgeball: "\uD83C\uDFD0",
  "Flag Football": "\uD83C\uDFC8",
  Kickball: "\u26BD",
  Pickleball: "\uD83C\uDFBE",
  Soccer: "\u26BD",
  Tennis: "\uD83C\uDFBE",
  Volleyball: "\uD83C\uDFD0",
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/health") {
      return json(await getHealth(env));
    }

    if (url.pathname === "/run") {
      if (!isManualRunAuthorized(request, env)) {
        return json({ ok: false, error: "manual run token required" }, 401);
      }

      const result = await runWatcher(env, { trigger: "manual" });
      return json(result, result.ok ? 200 : 500);
    }

    return new Response("solovolo Cloudflare Worker\n", {
      headers: { "content-type": "text/plain; charset=utf-8" },
    });
  },

  async scheduled(controller, env, ctx) {
    ctx.waitUntil(
      runWatcher(env, {
        trigger: `cron:${controller.cron}`,
        scheduledTime: new Date(controller.scheduledTime).toISOString(),
      }).then((result) => {
        if (!result.ok) {
          throw new Error(result.error || "scheduled check failed");
        }
      }),
    );
  },
};

async function runWatcher(env, meta = {}) {
  const startedAt = new Date().toISOString();
  const result = {
    ok: false,
    trigger: meta.trigger || "unknown",
    scheduledTime: meta.scheduledTime || null,
    startedAt,
    finishedAt: null,
    totalFetched: 0,
    newActivities: 0,
    updatedActivities: 0,
    notifiableActivities: 0,
    notifiedActivities: 0,
    skippedStartupNotifications: 0,
    pendingNotifications: 0,
    error: null,
  };

  try {
    if (!env.DB) {
      throw new Error("D1 binding DB is not configured");
    }

    const config = getConfig(env);
    const seen = await getSeenStatuses(env.DB);
    const isFirstRun = seen.size === 0;
    const rawActivities = await fetchActivities(config);
    const notificationCandidates = [];

    result.totalFetched = rawActivities.length;

    for (const raw of rawActivities) {
      const activity = normalizeActivity(parseActivity(raw));
      const seenStatus = seen.get(activity.id);
      const needsNotification = shouldNotify(activity, config);

      if (!seenStatus) {
        await saveNewActivity(env.DB, activity);
        result.newActivities += 1;
        console.log(`NEW: [${activity.type}] ${activity.sport}: ${activity.name}`);

        if (needsNotification) {
          notificationCandidates.push(activity);
        }
      } else {
        if (hasTrackedActivityChange(seenStatus, activity)) {
          await updateActivity(env.DB, activity);
          result.updatedActivities += 1;
        }

        if (seenStatus.notified === 0 && needsNotification) {
          notificationCandidates.push(activity);
          console.log(
            `NOW NOTIFIABLE: [${activity.type}] ${activity.sport}: ${activity.name}`,
          );
        }
      }
    }

    result.notifiableActivities = notificationCandidates.length;

    if (notificationCandidates.length > 0) {
      if (isFirstRun && !config.notifyOnStartup) {
        await markNotified(env.DB, notificationCandidates.map((activity) => activity.id));
        result.skippedStartupNotifications = notificationCandidates.length;
      } else if (env.DISCORD_WEBHOOK_URL) {
        const sent = await notifyNewActivities(
          env.DISCORD_WEBHOOK_URL,
          notificationCandidates,
        );

        if (sent) {
          await markNotified(env.DB, notificationCandidates.map((activity) => activity.id));
          result.notifiedActivities = notificationCandidates.length;
        } else {
          result.pendingNotifications = notificationCandidates.length;
        }
      } else {
        result.pendingNotifications = notificationCandidates.length;
        console.log("DISCORD_WEBHOOK_URL is not configured; notifications are pending.");
      }
    }

    result.ok = true;
  } catch (error) {
    result.error = errorMessage(error);
    console.error(result.error);
  } finally {
    result.finishedAt = new Date().toISOString();
    await saveRun(env, result);
  }

  return result;
}

function getConfig(env) {
  return {
    watchedSports: csv(env.WATCHED_SPORTS),
    excludedSports: new Set(csv(env.EXCLUDED_SPORTS || "Softball").map((s) => s.toLowerCase())),
    notifyOnStartup: booleanEnv(env.NOTIFY_ON_STARTUP, true),
    organization: env.VOLO_ORGANIZATION || "San Diego",
  };
}

function buildVariables(config, limit = 100, offset = 0) {
  const now = new Date().toISOString();
  const programTypes = ["PICKUP", "PRACTICE", "CLINIC", "DROPIN"];

  const leagueFilter = {
    organizationByOrganization: { name: { _eq: config.organization } },
    start_date: { _gte: now },
    program_type: { _in: programTypes },
    status: { _eq: "registration_open" },
    registrationByRegistration: {
      available_spots: { _gte: 1 },
      registration_close_date: { _gte: "now()" },
    },
  };

  if (config.watchedSports.length > 0) {
    leagueFilter.sportBySport = { name: { _in: config.watchedSports } };
  }

  const gameFilter = {
    start_time: { _gte: now },
    drop_in_capacity: {},
    leagueByLeague: {
      organizationByOrganization: { name: { _eq: config.organization } },
    },
  };

  if (config.watchedSports.length > 0) {
    gameFilter.leagueByLeague.sportBySport = { name: { _in: config.watchedSports } };
  }

  return {
    limit,
    offset,
    where: {
      _or: [
        {
          league_id: { _is_null: false },
          league: leagueFilter,
        },
        {
          game_id: { _is_null: false },
          game: gameFilter,
        },
      ],
    },
  };
}

async function fetchActivities(config) {
  const response = await fetch(API_URL, {
    method: "POST",
    headers: HEADERS,
    body: JSON.stringify({
      operationName: "DiscoverDaily",
      variables: buildVariables(config),
      query: DISCOVER_DAILY_QUERY,
    }),
  });

  if (!response.ok) {
    throw new Error(`Volo API returned HTTP ${response.status}: ${await responsePreview(response)}`);
  }

  const data = await response.json();

  if (data.errors) {
    throw new Error(`Volo GraphQL errors: ${JSON.stringify(data.errors).slice(0, 1000)}`);
  }

  const activities = data?.data?.discover_daily || [];
  const totalCount = data?.data?.discover_daily_aggregate?.aggregate?.count || 0;
  console.log(`Found ${activities.length} activities (total: ${totalCount})`);
  return activities;
}

function parseActivity(activity) {
  const result = {
    id: activity._id,
    league_id: activity.league_id || null,
    game_id: activity.game_id || null,
    type: null,
    sport: null,
    name: null,
    date: activity.event_start_date || null,
    start_time: activity.event_start_time_str || null,
    end_time: activity.event_end_time_str || null,
    venue: null,
    address: null,
    neighborhood: null,
    spots_available: null,
    max_spots: null,
    registrants: null,
    male_eligible_spots: null,
    url: null,
  };

  if (activity.league) {
    const league = activity.league;
    result.type = league.program_type || null;
    result.name = league.display_name || league.name || null;
    result.sport = league.sportBySport?.name || null;
    result.url = `https://www.volosports.com/l/${activity.league_id}`;

    if (league.venueByVenue) {
      result.venue = league.venueByVenue.shorthand_name || null;
      result.address = league.venueByVenue.formatted_address || null;
    }

    if (league.neighborhoodByNeighborhood) {
      result.neighborhood = league.neighborhoodByNeighborhood.name || null;
    }

    if (league.registrationByRegistration) {
      result.spots_available = league.registrationByRegistration.available_spots ?? null;
      result.max_spots = league.registrationByRegistration.max_registration_size ?? null;
    }

    if (league.registrants_aggregate) {
      result.registrants = league.registrants_aggregate.aggregate?.count ?? null;
    }
  } else if (activity.game) {
    const game = activity.game;
    result.type = "DROP-IN";
    result.url = `https://www.volosports.com/d/${activity.game_id}`;

    if (game.leagueByLeague) {
      const league = game.leagueByLeague;
      result.sport = league.sportBySport?.name || null;
      result.name = `${result.sport || "Activity"} Drop-In Game`;
    }

    if (game.venueByVenue) {
      result.venue = game.venueByVenue.shorthand_name || null;
      result.address = game.venueByVenue.formatted_address || null;
      result.neighborhood = game.venueByVenue.neighborhoodByNeighborhoodId?.name || null;
    }

    if (game.drop_in_capacity) {
      result.spots_available = game.drop_in_capacity.total_available_spots ?? null;
      result.male_eligible_spots =
        game.drop_in_capacity.total_male_eligible_spots ?? null;
    }

    if (game.start_time) {
      result.start_time = game.start_time;
    }

    if (game.end_time) {
      result.end_time = game.end_time;
    }
  }

  return result;
}

function normalizeActivity(activity) {
  return {
    ...activity,
    date: formatDate(activity.date),
    start_time: formatTime(activity.start_time),
    end_time: formatTime(activity.end_time),
    spots_available: nullableNumber(activity.spots_available),
    male_eligible_spots: nullableNumber(activity.male_eligible_spots),
  };
}

function shouldNotify(activity, config) {
  const activityType = (activity.type || "").toUpperCase();
  const name = (activity.name || "").trim().toLowerCase();
  const sport = (activity.sport || "").trim().toLowerCase();

  if (config.excludedSports.has(sport)) {
    return false;
  }

  if (name.includes("women") || name.includes("woman")) {
    return false;
  }

  if (activityType === "PICKUP") {
    return true;
  }

  if (activityType === "DROP-IN" || activityType === "DROPIN") {
    const maleEligible = activity.male_eligible_spots;
    return maleEligible === null ? true : maleEligible > 0;
  }

  return true;
}

async function getSeenStatuses(db) {
  const rows = await db
    .prepare(
      "SELECT id, notified, spots_available, male_eligible_spots FROM seen_activities",
    )
    .all();

  return new Map(
    (rows.results || []).map((row) => [
      row.id,
      {
        notified: Number(row.notified || 0),
        spotsAvailable: nullableNumber(row.spots_available),
        maleEligibleSpots: nullableNumber(row.male_eligible_spots),
      },
    ]),
  );
}

async function saveNewActivity(db, activity) {
  const now = new Date().toISOString();

  await db
    .prepare(
      `INSERT INTO seen_activities (
        id, sport, name, type, date, start_time, end_time, venue, address,
        neighborhood, spots_available, male_eligible_spots, url,
        first_seen_at, last_seen_at, notified
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)`,
    )
    .bind(
      activity.id,
      nullableString(activity.sport),
      nullableString(activity.name),
      nullableString(activity.type),
      nullableString(activity.date),
      nullableString(activity.start_time),
      nullableString(activity.end_time),
      nullableString(activity.venue),
      nullableString(activity.address),
      nullableString(activity.neighborhood),
      activity.spots_available,
      activity.male_eligible_spots,
      nullableString(activity.url),
      now,
      now,
    )
    .run();

  await db
    .prepare(
      "INSERT INTO activity_log (activity_id, event_type, details, created_at) VALUES (?, 'NEW', ?, ?)",
    )
    .bind(activity.id, `${activity.sport || "Other"}: ${activity.name || "Activity"}`, now)
    .run();
}

async function updateActivity(db, activity) {
  await db
    .prepare(
      `UPDATE seen_activities
       SET spots_available = ?, male_eligible_spots = ?, last_seen_at = ?
       WHERE id = ?`,
    )
    .bind(
      activity.spots_available,
      activity.male_eligible_spots,
      new Date().toISOString(),
      activity.id,
    )
    .run();
}

async function markNotified(db, activityIds) {
  if (activityIds.length === 0) {
    return;
  }

  await db.batch(
    activityIds.map((activityId) =>
      db.prepare("UPDATE seen_activities SET notified = 1 WHERE id = ?").bind(activityId),
    ),
  );
}

function hasTrackedActivityChange(seenStatus, activity) {
  return (
    seenStatus.spotsAvailable !== activity.spots_available ||
    seenStatus.maleEligibleSpots !== activity.male_eligible_spots
  );
}

async function notifyNewActivities(webhookUrl, activities) {
  const embeds = activities.slice(0, 10).map((activity) => buildActivityEmbed(activity));
  const counts = new Map();

  for (const activity of activities) {
    const sport = activity.sport || "Other";
    counts.set(sport, (counts.get(sport) || 0) + 1);
  }

  let summary = `**${activities.length} new activities found!**`;
  for (const [sport, count] of [...counts.entries()].sort(([a], [b]) => a.localeCompare(b))) {
    summary += `\n${sportEmoji(sport)} ${count} ${sport}`;
  }

  if (activities.length > embeds.length) {
    summary += `\nShowing first ${embeds.length} details.`;
  }

  return sendDiscordMessage(webhookUrl, {
    content: summary,
    embeds,
  });
}

function buildActivityEmbed(activity) {
  const spots = activity.spots_available;
  let description =
    `**${activity.type || "ACTIVITY"}** - ` +
    (spots === null ? "Spots unknown" : `${spots} spots available`);

  if (activity.male_eligible_spots !== null) {
    description += ` (${activity.male_eligible_spots} male-eligible)`;
  }

  const embed = {
    title: `${sportEmoji(activity.sport)} ${activity.name || "Activity"}`,
    description,
    color: 0x00ff00,
    fields: [
      {
        name: "\uD83D\uDCC5 When",
        value: `${activity.date || "?"} @ ${activity.start_time || "?"} - ${
          activity.end_time || "?"
        }`,
        inline: true,
      },
      {
        name: "\uD83D\uDCCD Where",
        value: `${activity.venue || "?"}\n${activity.neighborhood || ""}`,
        inline: true,
      },
    ],
  };

  if (activity.url) {
    embed.url = activity.url;
  }

  return embed;
}

async function sendDiscordMessage(webhookUrl, { content, embeds, username = "Volo Sports Bot" }) {
  const response = await fetch(webhookUrl, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username, content, embeds }),
  });

  if (!response.ok) {
    console.error(`Discord webhook returned HTTP ${response.status}`);
    return false;
  }

  return true;
}

async function getHealth(env) {
  if (!env.DB) {
    return { ok: false, error: "D1 binding DB is not configured" };
  }

  const seen = await env.DB.prepare("SELECT COUNT(*) AS count FROM seen_activities").first();
  const lastRun = await env.DB
    .prepare("SELECT * FROM watcher_runs ORDER BY id DESC LIMIT 1")
    .first();

  return {
    ok: true,
    service: "solovolo",
    schedule: "*/5 * * * *",
    seenActivities: Number(seen?.count || 0),
    lastRun: lastRun || null,
  };
}

async function saveRun(env, result) {
  if (!env.DB || !result.finishedAt) {
    return;
  }

  try {
    await env.DB
      .prepare(
        `INSERT INTO watcher_runs (
          started_at, finished_at, trigger, ok, total_fetched, new_activities,
          updated_activities, notifiable_activities, notified_activities,
          pending_notifications, error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      )
      .bind(
        result.startedAt,
        result.finishedAt,
        result.trigger,
        result.ok ? 1 : 0,
        result.totalFetched,
        result.newActivities,
        result.updatedActivities,
        result.notifiableActivities,
        result.notifiedActivities,
        result.pendingNotifications,
        result.error,
      )
      .run();
  } catch (error) {
    console.error(`Failed to save watcher run: ${errorMessage(error)}`);
  }
}

function formatDate(dateString) {
  if (!dateString) {
    return "?";
  }

  const date = parseVoloDate(dateString);
  if (!date) {
    return dateString;
  }

  return new Intl.DateTimeFormat("en-US", {
    timeZone: PACIFIC_TZ,
    weekday: "short",
    month: "short",
    day: "2-digit",
  })
    .format(date)
    .replace(",", "");
}

function formatTime(timeString) {
  if (!timeString) {
    return "?";
  }

  if (timeString.length <= 5 && timeString.includes(":")) {
    return timeString;
  }

  const date = parseVoloDate(timeString);
  if (!date) {
    return timeString;
  }

  return new Intl.DateTimeFormat("en-US", {
    timeZone: PACIFIC_TZ,
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }).format(date);
}

function parseVoloDate(value) {
  const normalized = /^\d{4}-\d{2}-\d{2}$/.test(value)
    ? `${value}T12:00:00.000Z`
    : value.replace("Z", "+00:00");
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

function sportEmoji(sport) {
  return SPORT_EMOJI[sport || ""] || "\uD83C\uDFC3";
}

function csv(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function booleanEnv(value, defaultValue) {
  if (value === undefined || value === null || String(value).trim() === "") {
    return defaultValue;
  }

  return !["0", "false", "no", "off"].includes(String(value).trim().toLowerCase());
}

function nullableNumber(value) {
  if (value === undefined || value === null || value === "") {
    return null;
  }

  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function nullableString(value) {
  return value === undefined || value === null ? null : String(value);
}

async function responsePreview(response) {
  const text = await response.text();
  return text.slice(0, 300);
}

function isManualRunAuthorized(request, env) {
  if (!env.MANUAL_RUN_TOKEN) {
    return false;
  }

  const headerToken = request.headers.get("x-solovolo-token") || "";
  const authorization = request.headers.get("authorization") || "";
  const bearerToken = authorization.match(/^Bearer\s+(.+)$/i)?.[1] || "";
  return headerToken === env.MANUAL_RUN_TOKEN || bearerToken === env.MANUAL_RUN_TOKEN;
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

function errorMessage(error) {
  return error instanceof Error ? error.message : String(error);
}
