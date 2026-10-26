# OpenAI plugin package (ChatGPT and Codex)

This folder is the DrinkedIn Night Out package for OpenAI's plugin directory, in the portable
Agent Plugins format that OpenAI's docs describe
(https://developers.openai.com/plugins/build/plugins). It sits apart from the Claude, Cursor and
Gemini files at the repo root and does not change them.

| Path | What it is |
| --- | --- |
| `plugin.json` | Manifest (`$schema` Agent Plugins 1.0.0) with listing, review and publication data under `extensions.com.openai` |
| `mcp.json` | The one remote server: streamable HTTP, `https://ai.drinkedin.net/mcp/night-out`, auth `none`, no headers |
| `skills/drinkedin-night-out/SKILL.md` | The Night Out skill (1.1.0 text), with location guidance for OpenAI clients: plan around a place the person names, never ask for a precise location |
| `skills/drinkedin-night-out/agents/openai.yaml` | Declares the skill's MCP dependency |
| `assets/icon.png` | Logo and composer icon (the repo icon, 512 x 512 PNG) |
| `scripts/validate.py` | Checks the package against the published schemas, OpenAI's field limits and DrinkedIn's copy rules |
| `scripts/build_zip.py` | Validates, then writes `dist/drinkedin-night-out-openai.zip` (git-ignored) |

Build:

```
python3 scripts/build_zip.py            # warns while demo_recording_url is a TODO
python3 scripts/build_zip.py --release  # fails until every TODO is replaced
```

`review.demo_recording_url` is a placeholder until the demo is recorded (SWE-1553). The MCP
origin `https://ai.drinkedin.net` can never change once submitted.
