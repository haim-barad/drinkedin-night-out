#!/usr/bin/env python3
"""Validate every per-channel manifest in this repo. Stdlib only; makes no network calls.

Channels checked:

* Claude Code: .claude-plugin/plugin.json, .claude-plugin/marketplace.json, .mcp.json
* Cursor (also read by Grok Bot): .cursor-plugin/plugin.json and the mcp.json it points at
* Gemini CLI: gemini-extension.json
* MCP Registry: server.json
* The shared skill: skills/<name>/SKILL.md (agentskills.io frontmatter rules)
* OpenAI (only when openai/ exists): runs openai/scripts/validate.py and checks that a built
  ZIP in openai/dist/ matches the package files byte for byte.

Across channels it checks that names, versions, descriptions and the MCP URL agree, that paths
stay inside the repo, that the icon is a square PNG, and DrinkedIn's copy rules: no numeric
drinking age, no payment or wallet words, no link to the other DrinkedIn MCP server.

Usage: python3 scripts/validate.py [--root DIR]. Exit 0 when there are no errors.
Tests (including negative ones): python3 -m unittest discover -s tests
"""

import importlib.util
import io
import json
import re
import struct
import sys
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

NAME = "drinkedin-night-out"
MCP_URL = "https://ai.drinkedin.net/mcp/night-out"
REPO_URL = "https://github.com/haim-barad/drinkedin-night-out"
REGISTRY_NAME = "io.github.haim-barad/drinkedin-night-out"

KEBAB = re.compile(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$")
SKILL_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
HTTPS = re.compile(r"^https://[^\s/@]+(/\S*)?$")
# "21+", "18+", "aged 21", "age of 18", "21 or older", "18 and over", "21 years old"
NUMERIC_AGE = re.compile(
    r"\b(1[6-9]|2[0-5])\s*\+|\bage(?:d)?\s+(?:of\s+)?(1[6-9]|2[0-5])\b"
    r"|\b(1[6-9]|2[0-5])\s+(?:or\s+older|and\s+(?:over|up|older)|years?\s+old)\b",
    re.I,
)
PAYMENT_WORDS = re.compile(r"\b(x402|usdc|wallet|crypto\w*|payments?|pay|pricing|credits?)\b", re.I)
SPONSOR_WORDS = re.compile(r"\bsponsor\w*\b|\bpromoted\b|\badvert\w*\b", re.I)
OTHER_SERVER = re.compile(r"https?://ai\.drinkedin\.net/mcp(?!/night-out)(?=[\s\"'`)/]|$)")

CURSOR_KEYS = {"name", "description", "version", "author", "homepage", "repository", "license",
               "keywords", "logo", "rules", "agents", "skills", "commands", "hooks", "mcpServers",
               "variables"}
GEMINI_KEYS = {"name", "version", "description", "mcpServers", "contextFileName", "excludeTools",
               "migratedTo", "plan", "settings", "themes"}
OPENAI_ZIP_ENTRIES = ("plugin.json", "mcp.json", "skills/", "assets/")


class Report:
    def __init__(self):
        self.errors, self.warnings, self.passed = [], [], []

    def err(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    def ok(self, msg):
        self.passed.append(msg)


def load_json(root, rel, rep):
    path = root / rel
    if not path.is_file():
        rep.err(f"{rel}: missing")
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        rep.err(f"{rel}: invalid JSON ({exc})")
        return None
    if not isinstance(doc, dict):
        rep.err(f"{rel}: top level must be an object")
        return None
    return doc


def inside(root, rel, field, rep, must_exist=True):
    """A manifest path: relative, no '..', resolves inside the repo and (optionally) exists."""
    if not isinstance(rel, str) or not rel.strip():
        rep.err(f"{field}: must be a non-empty relative path, got {rel!r}")
        return None
    if rel.startswith("/") or re.match(r"^[A-Za-z]:\\", rel) or ".." in Path(rel).parts:
        rep.err(f"{field}: {rel!r} must be relative to the repo with no '..'")
        return None
    path = (root / rel).resolve()
    if path != root.resolve() and root.resolve() not in path.parents:
        rep.err(f"{field}: {rel!r} leaves the repo")
        return None
    if must_exist and not path.exists():
        rep.err(f"{field}: {rel!r} does not exist")
        return None
    return path


def check_png(path, field, rep, lo=512, hi=2048):
    head = path.read_bytes()[:24]
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        rep.err(f"{field}: {path.name} is not a PNG")
        return
    w, h = struct.unpack(">II", head[16:24])
    if w != h or not lo <= w <= hi:
        rep.err(f"{field}: {path.name} is {w}x{h}; needs a square PNG, {lo} to {hi} px")
    else:
        rep.ok(f"{field}: {path.name} PNG {w}x{h}")


def check_https(value, field, rep):
    if not isinstance(value, str) or not HTTPS.match(value):
        rep.err(f"{field}: must be an https URL, got {value!r}")


def check_semver(value, field, rep):
    if not isinstance(value, str) or not SEMVER.match(value):
        rep.err(f"{field}: must be a semantic version, got {value!r}")


def check_copy(text, field, rep, manifest=False):
    """DrinkedIn copy rules for anything a listing or an agent reads."""
    if not isinstance(text, str):
        return
    for rx, what in ((NUMERIC_AGE, "a numeric drinking age (say 'legal drinking age where they are')"),
                     (PAYMENT_WORDS, "a payment word (the listed server takes no payments)"),
                     (OTHER_SERVER, "a link to the other DrinkedIn MCP server")):
        m = rx.search(text)
        if m:
            rep.err(f"{field}: contains {what}: {m.group(0)!r}")
    if manifest:
        m = SPONSOR_WORDS.search(text)
        if m:
            rep.err(f"{field}: contains a sponsorship word: {m.group(0)!r}")


def single_server(doc, rel, rep, url_key):
    servers = doc.get("mcpServers") if isinstance(doc, dict) else None
    if not isinstance(servers, dict) or len(servers) != 1:
        rep.err(f"{rel}: mcpServers must hold exactly one server")
        return None
    (key, server), = servers.items()
    if not isinstance(server, dict):
        rep.err(f"{rel}: mcpServers.{key} must be an object")
        return None
    if server.get(url_key) != MCP_URL:
        rep.err(f"{rel}: mcpServers.{key}.{url_key} must be {MCP_URL}, got {server.get(url_key)!r}")
    for banned in ("headers", "env", "command", "args"):
        if banned in server:
            rep.err(f"{rel}: mcpServers.{key}.{banned} is not allowed (authless remote server)")
    return server


# --- channels ---------------------------------------------------------------------------------


def check_claude(root, rep):
    p = load_json(root, ".claude-plugin/plugin.json", rep)
    m = load_json(root, ".claude-plugin/marketplace.json", rep)
    mcp = load_json(root, ".mcp.json", rep)
    if p:
        if p.get("name") != NAME:
            rep.err(f".claude-plugin/plugin.json: name must be {NAME!r}, got {p.get('name')!r}")
        check_semver(p.get("version"), ".claude-plugin/plugin.json: version", rep)
        if not (p.get("author") or {}).get("name"):
            rep.err(".claude-plugin/plugin.json: author.name is required")
        for k in ("homepage", "documentationUrl", "privacyPolicyUrl", "termsOfServiceUrl", "repository"):
            if k in p:
                check_https(p[k], f".claude-plugin/plugin.json: {k}", rep)
        if "icon" in p:
            path = inside(root, p["icon"], ".claude-plugin/plugin.json: icon", rep)
            if path:
                check_png(path, ".claude-plugin/plugin.json: icon", rep)
        check_copy(p.get("description"), ".claude-plugin/plugin.json: description", rep, manifest=True)
    if m:
        if not isinstance(m.get("name"), str) or not KEBAB.match(m["name"]):
            rep.err(f".claude-plugin/marketplace.json: name must be kebab-case, got {m.get('name')!r}")
        if not (m.get("owner") or {}).get("name"):
            rep.err(".claude-plugin/marketplace.json: owner.name is required")
        if not (m.get("metadata") or {}).get("description"):
            rep.err(".claude-plugin/marketplace.json: metadata.description is required")
        entries = [e for e in m.get("plugins") or [] if isinstance(e, dict) and e.get("name") == NAME]
        if len(entries) != 1:
            rep.err(f".claude-plugin/marketplace.json: needs exactly one plugins[] entry named {NAME}")
        else:
            e = entries[0]
            if e.get("source") != "./":
                rep.err(f".claude-plugin/marketplace.json: plugin source must be './', got {e.get('source')!r}")
            if p and e.get("version") != p.get("version"):
                rep.err(".claude-plugin/marketplace.json: plugin version differs from .claude-plugin/plugin.json")
            if p and e.get("description") != p.get("description"):
                rep.err(".claude-plugin/marketplace.json: plugin description differs from .claude-plugin/plugin.json")
    if mcp:
        server = single_server(mcp, ".mcp.json", rep, "url")
        if server is not None and server.get("type") != "http":
            rep.err(f".mcp.json: server type must be 'http', got {server.get('type')!r}")
    return p


def check_cursor(root, rep, ref):
    c = load_json(root, ".cursor-plugin/plugin.json", rep)
    if not c:
        return
    rel = ".cursor-plugin/plugin.json"
    if c.get("name") != NAME or not KEBAB.match(str(c.get("name"))):
        rep.err(f"{rel}: name must be {NAME!r}, got {c.get('name')!r}")
    for k in sorted(set(c) - CURSOR_KEYS):
        rep.err(f"{rel}: unknown field {k!r} (not in the Cursor plugin reference)")
    check_semver(c.get("version"), f"{rel}: version", rep)
    if not (c.get("author") or {}).get("name"):
        rep.err(f"{rel}: author.name is required")
    for k in ("homepage", "repository"):
        if k in c:
            check_https(c[k], f"{rel}: {k}", rep)
    logo = c.get("logo")
    if isinstance(logo, str) and logo.startswith(("http://", "https://")):
        check_https(logo, f"{rel}: logo", rep)
    elif logo is not None:
        path = inside(root, logo, f"{rel}: logo", rep)
        if path:
            check_png(path, f"{rel}: logo", rep)
    servers = c.get("mcpServers", "mcp.json")
    if isinstance(servers, str):
        path = inside(root, servers, f"{rel}: mcpServers", rep)
        if path:
            doc = load_json(root, path.relative_to(root.resolve()).as_posix(), rep)
            if doc:
                single_server(doc, servers, rep, "url")
    elif isinstance(servers, dict):
        single_server({"mcpServers": servers}, f"{rel}: mcpServers", rep, "url")
    else:
        rep.err(f"{rel}: mcpServers must be a path or an object")
    check_copy(c.get("description"), f"{rel}: description", rep, manifest=True)
    for k in ("version", "description"):
        if ref and c.get(k) != ref.get(k):
            rep.err(f"{rel}: {k} differs from .claude-plugin/plugin.json")


def check_gemini(root, rep, ref):
    g = load_json(root, "gemini-extension.json", rep)
    if not g:
        return
    rel = "gemini-extension.json"
    if g.get("name") != NAME or not SKILL_NAME.match(str(g.get("name"))):
        rep.err(f"{rel}: name must be {NAME!r} (lowercase, dashes), got {g.get('name')!r}")
    for k in sorted(set(g) - GEMINI_KEYS):
        rep.err(f"{rel}: unknown field {k!r} (not in the Gemini CLI extension reference)")
    check_semver(g.get("version"), f"{rel}: version", rep)
    server = single_server(g, rel, rep, "httpUrl")
    if server is not None:
        if "trust" in server:
            rep.err(f"{rel}: 'trust' is not supported in extension MCP servers")
        t = server.get("timeout")
        if t is not None and (not isinstance(t, int) or isinstance(t, bool) or t <= 0):
            rep.err(f"{rel}: timeout must be a positive integer (ms), got {t!r}")
    check_copy(g.get("description"), f"{rel}: description", rep, manifest=True)
    for k in ("version", "description"):
        if ref and g.get(k) != ref.get(k):
            rep.err(f"{rel}: {k} differs from .claude-plugin/plugin.json")


def check_registry(root, rep):
    s = load_json(root, "server.json", rep)
    if not s:
        return
    rel = "server.json"
    check_https(s.get("$schema"), f"{rel}: $schema", rep)
    if s.get("name") != REGISTRY_NAME:
        rep.err(f"{rel}: name must be {REGISTRY_NAME!r}, got {s.get('name')!r}")
    d = s.get("description")
    if not isinstance(d, str) or not 1 <= len(d) <= 100:
        rep.err(f"{rel}: description must be 1 to 100 characters")
    check_copy(d, f"{rel}: description", rep, manifest=True)
    check_semver(s.get("version"), f"{rel}: version", rep)
    if (s.get("repository") or {}).get("url") != REPO_URL:
        rep.err(f"{rel}: repository.url must be {REPO_URL}")
    remotes = s.get("remotes") or []
    if len(remotes) != 1 or remotes[0].get("type") != "streamable-http" or remotes[0].get("url") != MCP_URL:
        rep.err(f"{rel}: remotes must be one streamable-http remote at {MCP_URL}")
    for i, icon in enumerate(s.get("icons") or []):
        check_https(icon.get("src"), f"{rel}: icons[{i}].src", rep)
    if "websiteUrl" in s:
        check_https(s["websiteUrl"], f"{rel}: websiteUrl", rep)


def parse_frontmatter(text):
    """The small YAML subset SKILL.md uses: 'key: value' plus one level of nested string maps."""
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---", 4)
    if end < 0:
        return None, text
    data, parent = {}, None
    for line in text[4:end].splitlines():
        if not line.strip():
            continue
        m = re.match(r"^( *)([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not m:
            raise ValueError(f"cannot parse frontmatter line {line!r}")
        indent, key, value = m.groups()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if len(indent) > 2:
            raise ValueError(f"nesting deeper than one level is not allowed: {line.strip()!r}")
        if indent and parent is not None:
            data[parent][key] = value if value else {}  # an empty nested value is a map, not a string
        elif not value:
            data[key], parent = {}, key
        else:
            data[key], parent = value, None
    return data, text[end + 4:]


def check_skill(root, rep):
    skills = sorted((root / "skills").glob("*/SKILL.md"))
    if not skills:
        rep.err("skills/: no skills/<name>/SKILL.md found")
    for path in skills:
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        try:
            fm, body = parse_frontmatter(text)
        except ValueError as exc:
            rep.err(f"{rel}: {exc}")
            continue
        if fm is None:
            rep.err(f"{rel}: no YAML frontmatter")
            continue
        name = fm.get("name")
        if not isinstance(name, str) or not 1 <= len(name) <= 64 or not SKILL_NAME.match(name):
            rep.err(f"{rel}: name must be 1-64 chars of a-z, 0-9 and single hyphens, got {name!r}")
        elif name != path.parent.name:
            rep.err(f"{rel}: name {name!r} must match its folder {path.parent.name!r}")
        desc = fm.get("description")
        if not isinstance(desc, str) or not 1 <= len(desc) <= 1024:
            rep.err(f"{rel}: description must be 1 to 1024 characters")
        comp = fm.get("compatibility")
        if comp is not None and (not isinstance(comp, str) or len(comp) > 500):
            rep.err(f"{rel}: compatibility must be at most 500 characters")
        meta = fm.get("metadata", {})
        if not isinstance(meta, dict) or not all(isinstance(v, str) for v in meta.values()):
            rep.err(f"{rel}: metadata must map strings to strings")
        elif "version" in meta:
            check_semver(meta["version"], f"{rel}: metadata.version", rep)
        if len(text.splitlines()) > 500:
            rep.warn(f"{rel}: over 500 lines (agentskills.io guidance)")
        check_copy(text, rel, rep)


def check_readme(root, rep):
    path = root / "README.md"
    if not path.is_file():
        rep.err("README.md: missing")
        return
    check_copy(path.read_text(encoding="utf-8"), "README.md", rep)


def check_openai(root, rep):
    pkg = root / "openai"
    if not pkg.is_dir():
        rep.ok("openai/: not in this tree (lives on its own branch); skipped")
        return
    script = pkg / "scripts" / "validate.py"
    if not script.is_file():
        rep.err("openai/: present but openai/scripts/validate.py is missing")
    else:
        spec = importlib.util.spec_from_file_location("openai_validate", script)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        out = io.StringIO()
        try:
            with redirect_stdout(out):
                spec.loader.exec_module(mod)
                code = mod.main([])
        except SystemExit as exc:  # a validator that exits instead of returning
            code = exc.code
        except Exception as exc:  # noqa: BLE001 - report any crash as a failure
            code = f"crashed: {exc!r}"
        if code not in (0, None):
            tail = " | ".join(out.getvalue().strip().splitlines()[-5:])
            rep.err(f"openai/scripts/validate.py failed ({code}): {tail}")
        else:
            rep.ok("openai/scripts/validate.py passed")
    mcp = load_json(root, "openai/mcp.json", rep)
    if mcp:
        single_server(mcp, "openai/mcp.json", rep, "url")
    for zpath in sorted((pkg / "dist").glob("*.zip")):
        rel = zpath.relative_to(root).as_posix()
        with zipfile.ZipFile(zpath) as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")]
            for n in ("plugin.json", "mcp.json"):
                if n not in names:
                    rep.err(f"{rel}: {n} must be at the ZIP root")
            for n in names:
                if not n.startswith(OPENAI_ZIP_ENTRIES) or ".." in Path(n).parts:
                    rep.err(f"{rel}: unexpected entry {n!r}")
                elif not (pkg / n).is_file():
                    rep.err(f"{rel}: {n} is not in openai/ (stale ZIP)")
                elif zf.read(n) != (pkg / n).read_bytes():
                    rep.err(f"{rel}: {n} differs from openai/{n} (stale ZIP: rebuild it)")


def validate(root):
    root = Path(root)
    rep = Report()
    ref = None
    for label, run in (("Claude Code plugin + marketplace", lambda: check_claude(root, rep)),
                       ("Cursor plugin", lambda: check_cursor(root, rep, ref)),
                       ("Gemini CLI extension", lambda: check_gemini(root, rep, ref)),
                       ("MCP Registry server.json", lambda: check_registry(root, rep)),
                       ("skills/*/SKILL.md", lambda: check_skill(root, rep)),
                       ("README.md copy rules", lambda: check_readme(root, rep)),
                       ("OpenAI package", lambda: check_openai(root, rep))):
        before = len(rep.errors)
        result = run()
        if label.startswith("Claude"):
            ref = result
        if len(rep.errors) == before:
            rep.ok(f"{label}: no errors")
    return rep


def main(argv):
    root = Path(__file__).resolve().parents[1]
    if argv[:1] == ["--root"] and len(argv) > 1:
        root = Path(argv[1])
    rep = validate(root)
    for msg in rep.passed:
        print(f"ok    {msg}")
    for msg in rep.warnings:
        print(f"WARN  {msg}")
    for msg in rep.errors:
        print(f"ERROR {msg}")
    print(f"\n{len(rep.errors)} error(s), {len(rep.warnings)} warning(s)")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
