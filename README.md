# DrinkedIn Night Out

This plugin connects Claude Code to the DrinkedIn Night Out MCP server at `https://ai.drinkedin.net/mcp/night-out` (Streamable HTTP). The server is read-only and free, and it needs no account or key.

## Install (Claude Code)

```
/plugin marketplace add haim-barad/drinkedin-night-out
/plugin install drinkedin-night-out@drinkedin
```

## What it does

Ask for a night out near a place. The planner builds a walkable route of 2 to 4 stops. Every venue on the route has been validated against the venue's own website or an official liquor-licence register.

There are two tools:

- `drinkedin_plan_night_out` plans the route.
  - Give it latitude and longitude (preferred), a street address or landmark, or a place name with its region or country.
  - Optional: `style` (`bar_crawl`, `craft_beer_crawl`, `dinner_and_drinks`, `club_night`), `stops` (2 to 4) and `max_walk_m` (200 to 2000).
- `drinkedin_get_guide` explains how to call the planner and the rules for relaying a plan.

Example prompts:

- "Plan me a night out near Kennedy Plaza in Providence, RI."
- "Do a bar crawl starting from Kennedy Plaza, Providence, RI."
- "Dinner and then drinks near Kennedy Plaza, just two stops."

## What to expect

- **Statuses:** a reply is `planned`, `partial`, `needs_input`, `no_coverage` or `error`. The planner works best where coverage is validated. Where coverage is thin it says so instead of padding the route.
- **Estimates:** walking times are estimates. Hours and prices are never asserted, so check the venue's own site.
- **Geocoding:** a typed address is sent to OpenStreetMap Nominatim to find the point. The reply's `geocoded_as` shows what it matched.
- **Age:** alcohol is for people of legal drinking age where they are.

## Links

- Guide: https://drinkedin.net/instructions.md
- Privacy: https://drinkedin.net/p/privacy.html
- Terms: https://drinkedin.net/p/terms.html
- Support: support@drinkedin.net

Published by Haim Barad. No sponsored placement.
