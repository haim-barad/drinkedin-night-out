# Changelog

## OpenAI package 1.0.0 (openai/, SKILL.md 1.1.0 openai variant)

- New `openai/` folder: the package for OpenAI's plugin directory (ChatGPT and Codex) in the portable Agent Plugins format: `plugin.json` with listing, review (5 positive and 3 negative test cases, `commerce: false`) and publication data (countries US and ES) under `extensions.com.openai`; `mcp.json` (streamable HTTP, auth none, no headers); the skill with `agents/openai.yaml`; the repo icon.
- The OpenAI skill plans around a town or city the person names, or the approximate town the app shares, and never asks for a precise location, GPS coordinates or a street address. It matches the server's OpenAI client variant of `drinkedin_plan_night_out`.
- `openai/scripts/validate.py` and `build_zip.py` validate the package and write `openai/dist/drinkedin-night-out-openai.zip` (git-ignored). The root Claude, Cursor and Gemini files are unchanged.

## 0.3.0 (SKILL.md 1.1.0)

- The skill describes `route.plan_url` (with `route.plan_id`), which a `planned` or `partial` route can now carry: a drinkedin.net page with the stops, the walks between them and a route map. The assistant offers it when the person wants to share or save the plan and gives it as a link the person may open, exactly as returned.
- Privacy section: the sentence "nothing is written" is replaced by what the plan link keeps (the venues' public data, the walks, the style label, the shared town, the created and expiry dates), for how long (30 days after the route was last planned, then deleted) and what it never keeps (the person's coordinates, typed address, place name or `near` label, IP address, client details).
- README: a "Plan links" line under "What to expect".
- "Read-only" is gone wherever it described the planner: the SKILL.md description and intro, the README and the plugin descriptions now say what is saved (a planned route, public venue data only, 30 days, never the person's location). This matches the server, whose `drinkedin_plan_night_out` annotations are `readOnlyHint: false`, `destructiveHint: false`, `idempotentHint: true` while plan links are on. `drinkedin_get_guide` stays read-only. `server.json` (the MCP Registry entry) drops "Read-only" too: "Plans walkable 2-4 stop nights out between validated, licensed venues. No sign-in."
- Version 0.3.0 in `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.cursor-plugin/plugin.json` and `gemini-extension.json`. `server.json` (the MCP Registry entry) goes 1.0.0 → 1.1.0 for the new description; the server URL is unchanged. It is republished after the server change is live (Haim approved, 26 Oct).

## 0.2.0 (SKILL.md 1.0.1)

- Ships the Night Out skill in the plugin; Cursor plugin manifest and Gemini CLI extension.
