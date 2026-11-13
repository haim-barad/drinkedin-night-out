# Changelog

## Unreleased

- `scripts/validate.py` checks every per-channel manifest in one run (Claude Code plugin and marketplace, Cursor, Gemini CLI, MCP Registry `server.json`, the skill, and the OpenAI package and ZIP when `openai/` is present), plus cross-channel agreement and the copy rules. Stdlib only, no network. Negative tests in `tests/test_validate.py` (`python3 -m unittest discover -s tests`). Repo tooling only: no manifest references it, and no version bump.

## 0.6.0 (SKILL.md 1.5.1, Claude-directory variant)

- **Why:** the Claude plugin directory accepted 0.3.0 (SKILL.md 1.1.0) and rejected 0.4.0 under its directory policy. This version keeps the 1.5.0 improvements and returns the two lines that changed in 0.4.0 to their 1.1.0 form.
- **The skill `description` says only what it plans, when to use it, and that plans are for adults of legal drinking age where they are.** It gives no behaviour instructions and has no clause that makes it load for under-age requests.
- **The under-age section is the 1.1.0 wording.** It doesn't call the planner, it says in one sentence that DrinkedIn plans are for adults of legal drinking age, and it states no age as a number. Places from general knowledge are never presented as a DrinkedIn plan.
- **No `client_skill_version`.** The live tool schemas don't accept it, so the Updates section and its privacy bullet are gone too. The plugin updates through its marketplace.
- **From 1.5.0, unchanged:**
  - the guide is described as reference data (places, styles, vibes);
  - "When you relay a plan" uses `share_text` when the reply includes it;
  - per-stop links;
  - hours and prices marked unverified.
- **DELIBERATE PER-PLATFORM DIFFERENCE. Do not harmonise.** The website and ClawHub copy of the skill (drinkedin.net/skills/drinkedin-night-out/SKILL.md) keeps the stronger under-age trigger in its description, because evals on other hosts need it. This repo's copy follows the Claude directory policy.
- Version 0.6.0 in `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.cursor-plugin/plugin.json` and `gemini-extension.json`. `server.json` is unchanged at 1.1.0.

## 0.4.0 (SKILL.md 1.2.0)

- The skill's `description` (the text hosts read when deciding to load it) now also covers a request from someone under the legal drinking age where they are: then no venues are planned or suggested, and no age is stated as a number. In the SWE-1547 eval, Claude Code and Hermes did not load the skill for such a request and answered from their own knowledge; a rule that must hold when the skill would not otherwise trigger has to be in the description.
- The under-age section now also says not to suggest venues from general knowledge, and reads "Keep it to one sentence" instead of "do not lecture" (scanners flag caveat-suppressing phrases).
- Version 0.4.0 in `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.cursor-plugin/plugin.json` and `gemini-extension.json`. `server.json` (the MCP Registry entry) is unchanged at 1.1.0: the server URL and description did not change.

## 0.3.0 (SKILL.md 1.1.0)

- The skill describes `route.plan_url` (with `route.plan_id`), which a `planned` or `partial` route can now carry: a drinkedin.net page with the stops, the walks between them and a route map. The assistant offers it when the person wants to share or save the plan and gives it as a link the person may open, exactly as returned.
- Privacy section: the sentence "nothing is written" is replaced by what the plan link keeps (the venues' public data, the walks, the style label, the shared town, the created and expiry dates), for how long (30 days after the route was last planned, then deleted) and what it never keeps (the person's coordinates, typed address, place name or `near` label, IP address, client details).
- README: a "Plan links" line under "What to expect".
- "Read-only" is gone wherever it described the planner: the SKILL.md description and intro, the README and the plugin descriptions now say what is saved (a planned route, public venue data only, 30 days, never the person's location). This matches the server, whose `drinkedin_plan_night_out` annotations are `readOnlyHint: false`, `destructiveHint: false`, `idempotentHint: true` while plan links are on. `drinkedin_get_guide` stays read-only. `server.json` (the MCP Registry entry) drops "Read-only" too: "Plans walkable 2-4 stop nights out between officially validated venues. No sign-in."
- "Licensed venues" is gone from the descriptions. DrinkedIn validates a venue against an official licence register, a premises census (an official list of premises, not a licence register) or the venue's own site, so not every venue on a route is a licence-register record. `server.json`, the plugin manifests and the marketplace entry now say "officially validated venues"; the SKILL.md description and intro and the README say "an official licence register or premises census, or the venue's own site".
- Version 0.3.0 in `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.cursor-plugin/plugin.json` and `gemini-extension.json`. `server.json` (the MCP Registry entry) goes 1.0.0 → 1.1.0 for the new description; the server URL is unchanged. It is republished after the server change is live (Haim approved, 26 Oct).

## 0.2.0 (SKILL.md 1.0.1)

- Ships the Night Out skill in the plugin; Cursor plugin manifest and Gemini CLI extension.
