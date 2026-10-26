#!/usr/bin/env python3
"""Validate the OpenAI plugin package in openai/ (SWE-1555). Stdlib only; jsonschema if present.

OpenAI publishes no package validator CLI. This checks the package against:

* the published Agent Plugins 1.0.0 JSON schemas (vendored in scripts/schemas/, fetched from
  https://agent-plugins.org/schemas/1.0.0/{plugin,mcp}.schema.json), when ``jsonschema`` is
  installed;
* the submission limits in developers.openai.com/plugins/deploy/submission ("Manifest fields",
  "Listing metadata", "Icons and screenshots", review and publication fields);
* the MCP rules in /plugins/build/plugins and /plugins/deploy/submission (one remote
  streamable-http server, auth none, no headers, no apps or hooks);
* DrinkedIn's copy rules (no numeric drinking age, no pricing or comparison words, no coverage,
  rank or count words, no 'near me' or current-location wording).

Known conflict: the OpenAI docs put ``extensions.com.openai.auth`` on each server in mcp.json, but
the published mcp.schema.json forbids extra server keys. The schema check strips that one key and
reports it; the OpenAI-specific auth block is checked separately.

Usage: python3 scripts/validate.py [--release]. --release also fails on TODO placeholders.
Exit 0 when there are no errors.
"""

import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = Path(__file__).resolve().parent / "schemas"
MCP_URL = "https://ai.drinkedin.net/mcp/night-out"
TOOLS = {"drinkedin_plan_night_out", "drinkedin_get_guide"}
PACKAGE_ENTRIES = ("plugin.json", "mcp.json", "skills", "assets")
MAX_IMAGE_BYTES = 5 * 1024 * 1024

errors, warnings, passed = [], [], []


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def ok(msg):
    passed.append(msg)


def load(name):
    path = ROOT / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        err(f"{name}: cannot read JSON ({exc})")
        return None


def schema_check(doc, schema_file, label):
    try:
        import jsonschema
    except ImportError:
        warn(f"{label}: jsonschema not installed; schema check skipped (manual checks still run)")
        return
    schema = json.loads((SCHEMAS / schema_file).read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    problems = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
    for p in problems:
        err(f"{label}: schema: {'/'.join(map(str, p.path)) or '(root)'}: {p.message}")
    if not problems:
        ok(f"{label}: valid against {schema['$id']}")


def luminance(hex_colour):
    channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def png_size(path):
    with open(path, "rb") as fh:
        head = fh.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", head[16:24])


def check_rel_path(value, field):
    if not isinstance(value, str) or not value.startswith("./"):
        err(f"{field}: must be a ./-relative path, got {value!r}")
        return None
    path = (ROOT / value).resolve()
    if ROOT.resolve() not in path.parents:
        err(f"{field}: {value} leaves the plugin root")
        return None
    if not path.is_file():
        err(f"{field}: {value} does not exist")
        return None
    return path


def check_icon(value, field):
    path = check_rel_path(value, field)
    if path is None:
        return
    size = path.stat().st_size
    if size > MAX_IMAGE_BYTES:
        err(f"{field}: {value} is {size} bytes, over 5 MiB")
    dims = png_size(path) if path.suffix.lower() == ".png" else None
    if dims is None:
        err(f"{field}: {value} is not a PNG this script can read")
        return
    w, h = dims
    if w != h or w < 48 or w > 4096:
        err(f"{field}: {value} is {w}x{h}; icons must be square, 48 to 4096 px")
    else:
        ok(f"{field}: {value} PNG {w}x{h}, {size} bytes")


def check_url(value, field):
    if not isinstance(value, str) or not re.match(r"^https://[^\s/@]+(/\S*)?$", value):
        err(f"{field}: must be an HTTPS URL without credentials, got {value!r}")
    elif len(value) > 1024:
        err(f"{field}: longer than 1024 characters")
    else:
        ok(f"{field}: {value}")


def limit(value, n, field, required=True):
    if value is None:
        if required:
            err(f"{field}: required")
        return
    if not isinstance(value, str) or not value.strip():
        err(f"{field}: must be a non-empty string")
    elif len(value) > n:
        err(f"{field}: {len(value)} characters, limit {n}")
    else:
        ok(f"{field}: {len(value)}/{n} characters")


# --- copy rules ---------------------------------------------------------------------------------

BANNED = [
    (r"\b\d{2}\s*\+", "numeric age like '21+' (say 'legal drinking age where they are')"),
    (r"\b(?:aged?|over|under)\s+\d{2}\b", "numeric age"),
    (r"(?i)near me", "'near me' (plan around a place the person names)"),
    (r"(?i)current location", "current-location wording"),
    (r"(?i)\b(?:gps|latitude|longitude)\b", "precise-location wording"),
]
LISTING_BANNED = [
    (r"(?i)\bfree\b|\bprice[sd]?\b(?! are not)|\bdiscount|\bsubscri|\btrial\b|\bpromo", "pricing"),
    (r"(?i)\bbest\b|\bbetter than\b|\bunlike\b|\b#1\b|\bleading\b|\bonly app\b", "comparison"),
    (r"(?i)\bcover(?:ed|age|s|ing)?\b|\branked?\b|\btop\b|\blargest\b|\bmost\b", "coverage or rank"),
    (r"(?i)\b\d[\d,]*\s+(?:bars|venues|cities|places|towns|countries)\b", "count claim"),
]
#: Phrases the copy rules allow although a banned pattern matches them.
ALLOWED_PHRASES = ("never as a ranking or a coverage claim", "Prices are not verified")


def copy_scan(text, label, listing=False):
    for allowed in ALLOWED_PHRASES:
        text = text.replace(allowed, "")
    rules = BANNED + (LISTING_BANNED if listing else [])
    hits = [why for pattern, why in rules if re.search(pattern, text)]
    for why in hits:
        if label.startswith("SKILL.md") and why == "precise-location wording":
            continue  # the skill says 'Never ask for ... GPS coordinates': a rule, not a request
        err(f"{label}: copy rule: {why}")
    if not hits:
        ok(f"{label}: copy rules")


# --- checks -------------------------------------------------------------------------------------


def check_plugin(manifest, release):
    schema_check(manifest, "plugin.schema.json", "plugin.json")
    name = manifest.get("name", "")
    if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", name) or len(name) > 64:
        err("name: lowercase letters, numbers and single hyphens, at most 64")
    if not re.match(r"^\d+\.\d+\.\d+$", manifest.get("version", "")):
        err("version: use an explicit semantic version")
    # Docs: 4000 (manifest table); the SWE-1555 ticket keeps it under 1024 to be safe.
    limit(manifest.get("description"), 1024, "description")
    author = manifest.get("author") or {}
    limit(author.get("name"), 120, "author.name")
    openai = (manifest.get("extensions") or {}).get("com.openai")
    if not isinstance(openai, dict):
        err("extensions.com.openai: missing")
        return
    for forbidden in ("apps", "hooks"):
        if forbidden in openai:
            err(f"extensions.com.openai.{forbidden}: packages with apps or hooks cannot be submitted")
    ui = openai.get("interface") or {}
    limit(ui.get("displayName"), 30, "interface.displayName")
    limit(ui.get("shortDescription"), 30, "interface.shortDescription")
    limit(ui.get("longDescription"), 4000, "interface.longDescription")
    limit(ui.get("developerName"), 80, "interface.developerName")
    limit(ui.get("category"), 80, "interface.category")
    caps = ui.get("capabilities", [])
    if not isinstance(caps, list) or len(caps) > 20 or any(
        not isinstance(c, str) or not c or len(c) > 120 for c in caps
    ):
        err("interface.capabilities: at most 20 strings of at most 120 characters")
    for field in ("websiteURL", "supportURL", "privacyPolicyURL", "termsOfServiceURL"):
        check_url(ui.get(field), f"interface.{field}")
    prompts = ui.get("defaultPrompt") or []
    prompts = [prompts] if isinstance(prompts, str) else prompts
    if len(prompts) != 3 or len(set(prompts)) != 3:
        err("interface.defaultPrompt: give three unique prompts")
    for i, p in enumerate(prompts):
        limit(p, 128, f"interface.defaultPrompt[{i}]")
        if "@" in p:
            err(f"interface.defaultPrompt[{i}]: no @mentions")
    for field, against in (("brandColor", "#FFFFFF"), ("brandColorDark", "#212121")):
        colour = ui.get(field)
        if colour is None:
            continue
        if not re.match(r"^#[0-9A-Fa-f]{6}$", colour):
            err(f"interface.{field}: use #RRGGBB")
            continue
        ratio = contrast(colour, against)
        (ok if ratio >= 2 else err)(f"interface.{field} {colour}: contrast {ratio:.2f}:1 vs {against}")
    for field in ("composerIcon", "logo", "composerIconDark", "logoDark"):
        if field in ui:
            check_icon(ui[field], f"interface.{field}")
    if "logo" not in ui or "composerIcon" not in ui:
        err("interface: logo and composerIcon are required for submission")
    if ui.get("screenshots"):
        err("interface.screenshots: the plugin has no UI, so no screenshots")
    listing = " ".join(
        [ui.get("displayName", ""), ui.get("shortDescription", ""), ui.get("longDescription", "")]
        + list(caps)
        + prompts
        + [manifest.get("description", "")]
    )
    copy_scan(listing, "listing text", listing=True)
    check_review(openai.get("review") or {}, release)
    check_publication(openai.get("publication") or {})


def check_review(review, release):
    for forbidden in ("test_credentials", "reviewer_instructions"):
        if forbidden in review:
            err(f"review.{forbidden}: rejected in ZIP metadata")
    cases = review.get("test_cases") or {}
    pos, neg = cases.get("positive") or [], cases.get("negative") or []
    (ok if len(pos) == 5 else err)(f"review.test_cases.positive: {len(pos)} (exactly 5)")
    (ok if len(neg) == 3 else err)(f"review.test_cases.negative: {len(neg)} (exactly 3)")
    for kind, items in (("positive", pos), ("negative", neg)):
        for i, case in enumerate(items):
            label = f"review.test_cases.{kind}[{i}]"
            limit(case.get("description"), 4000, f"{label}.description")
            limit(case.get("prompt"), 4000, f"{label}.prompt")
            if kind == "positive":
                limit(case.get("tools_triggered"), 4000, f"{label}.tools_triggered")
                limit(case.get("expected_behavior"), 4000, f"{label}.expected_behavior")
                named = {t.strip() for t in str(case.get("tools_triggered", "")).split(",")}
                if not named or not named <= TOOLS:
                    err(f"{label}.tools_triggered: unknown tool in {sorted(named)}")
            text = " ".join(str(v) for v in case.values())
            copy_scan(text, label)
    under_age = any("legal drinking age" in c.get("expected_behavior", "") for c in neg)
    vodka = any("vodka" in c.get("prompt", "").lower() for c in neg)
    (ok if under_age and vodka else err)("negative cases include under-age and 'order me vodka'")
    demo = review.get("demo_recording_url")
    if not isinstance(demo, str) or not demo:
        err("review.demo_recording_url: required for MCP review")
    elif "TODO" in demo:
        (err if release else warn)(
            "review.demo_recording_url is a TODO placeholder: replace it (SWE-1553) before upload"
        )
    else:
        check_url(demo, "review.demo_recording_url")
    if review.get("commerce") is not False:
        err("review.commerce: must be the boolean false")


def check_publication(pub):
    countries = pub.get("countries")
    if not isinstance(countries, list) or not countries:
        err("publication.countries: give an allowlist")
    elif any(not isinstance(c, str) or not re.match(r"^[A-Z]{2}$", c) for c in countries):
        err("publication.countries: uppercase two-letter codes")
    else:
        ok(f"publication.countries: {countries}")
    limit(pub.get("release_notes"), 4000, "publication.release_notes")


def check_mcp(doc):
    servers = (doc or {}).get("mcpServers") or {}
    stripped = json.loads(json.dumps(doc))
    for server in (stripped.get("mcpServers") or {}).values():
        if isinstance(server, dict):
            server.pop("extensions", None)
    schema_check(stripped, "mcp.schema.json", "mcp.json (server 'extensions' stripped)")
    if len(servers) != 1:
        err(f"mcp.json: exactly one server for plugin-level review cases, found {len(servers)}")
        return
    (name, server), = servers.items()
    if server.get("type") != "streamable-http":
        err("mcp.json: type must be streamable-http")
    if server.get("url") != MCP_URL:
        err(f"mcp.json: url must be {MCP_URL} (the origin can never change after submission)")
    if server.get("headers"):
        err("mcp.json: public submission rejects non-empty server headers")
    auth = ((server.get("extensions") or {}).get("com.openai") or {}).get("auth") or {}
    (ok if auth == {"type": "none"} else err)(f"mcp.json: {name} auth {auth or 'missing'}")
    if "extensions" in server:
        warn(
            "mcp.json: the published mcp.schema.json forbids a server 'extensions' key, but "
            "OpenAI's docs put auth there; kept per the docs"
        )


def check_skills():
    skill_dirs = sorted(p for p in (ROOT / "skills").iterdir() if p.is_dir())
    if not skill_dirs:
        err("skills/: no skill")
    for d in skill_dirs:
        md = d / "SKILL.md"
        if not md.is_file():
            err(f"{d.name}: SKILL.md missing")
            continue
        text = md.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        if not m:
            err(f"{d.name}/SKILL.md: YAML front matter missing")
            continue
        front = m.group(1)
        name = re.search(r"^name:\s*(\S+)\s*$", front, re.M)
        desc = re.search(r"^description:\s*(.+)$", front, re.M)
        if not name or name.group(1) != d.name:
            err(f"{d.name}/SKILL.md: name must match the folder")
        if not desc or len(desc.group(1)) > 1024:
            err(f"{d.name}/SKILL.md: description missing or over 1024 characters")
        else:
            ok(f"{d.name}/SKILL.md: name and description ({len(desc.group(1))} chars)")
        copy_scan(text, f"SKILL.md ({d.name})")
        agents = d / "agents" / "openai.yaml"
        if agents.is_file():
            y = agents.read_text(encoding="utf-8")
            needed = ('type: "mcp"', 'transport: "streamable_http"', f'url: "{MCP_URL}"')
            missing = [n for n in needed if n not in y]
            (err if missing else ok)(f"{d.name}/agents/openai.yaml MCP dependency {missing or ''}")


def check_tree():
    for bad in (".app.json", "hooks", ".codex-plugin"):
        if (ROOT / bad).exists():
            err(f"{bad}: not allowed in a directory submission package")
    for p in (ROOT / "skills").rglob("*"):
        if p.is_file() and re.search(r"(?i)secret|token|\.env$", p.name):
            err(f"{p.relative_to(ROOT)}: looks like a credential file")


def main(argv):
    release = "--release" in argv
    manifest = load("plugin.json")
    if manifest is not None:
        check_plugin(manifest, release)
    check_mcp(load("mcp.json"))
    check_skills()
    check_tree()
    for line in passed:
        print(f"ok    {line}")
    for line in warnings:
        print(f"WARN  {line}")
    for line in errors:
        print(f"ERROR {line}")
    print(f"\n{len(passed)} passed, {len(warnings)} warnings, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
