"""Tests for scripts/validate.py: the real tree passes, and each broken copy fails for its reason.

Run: python3 -m unittest discover -s tests
"""

import json
import shutil
import struct
import sys
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import validate  # noqa: E402

IGNORE = shutil.ignore_patterns(".git", "dist", "__pycache__", ".DS_Store")


def png(w, h):
    raw = b"".join(b"\x00" + b"\x00\x00\x00" * w for _ in range(h))
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class ValidateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "repo"
        shutil.copytree(REPO, self.root, ignore=IGNORE)
        shutil.rmtree(self.root / "openai", ignore_errors=True)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def edit_json(self, rel, fn):
        path = self.root / rel
        doc = json.loads(path.read_text())
        fn(doc)
        path.write_text(json.dumps(doc, indent=2))

    def errors(self):
        return validate.validate(self.root).errors

    def assertFails(self, needle):
        errs = self.errors()
        self.assertTrue(any(needle in e for e in errs), f"expected an error containing {needle!r}, got {errs}")

    # --- positive ---

    def test_real_tree_passes(self):
        rep = validate.validate(REPO)
        self.assertEqual(rep.errors, [])

    def test_copy_passes(self):
        self.assertEqual(self.errors(), [])

    # --- Claude Code ---

    def test_missing_manifest(self):
        (self.root / ".claude-plugin" / "plugin.json").unlink()
        self.assertFails(".claude-plugin/plugin.json: missing")

    def test_marketplace_source_must_be_root(self):
        self.edit_json(".claude-plugin/marketplace.json", lambda d: d["plugins"][0].update(source="./plugin"))
        self.assertFails("plugin source must be './'")

    def test_marketplace_version_drift(self):
        self.edit_json(".claude-plugin/marketplace.json", lambda d: d["plugins"][0].update(version="9.9.9"))
        self.assertFails("marketplace.json: plugin version differs")

    def test_mcp_json_headers_rejected(self):
        self.edit_json(".mcp.json", lambda d: d["mcpServers"]["drinkedin-night-out"].update(headers={"x": "y"}))
        self.assertFails(".mcp.json: mcpServers.drinkedin-night-out.headers is not allowed")

    def test_icon_must_be_square(self):
        (self.root / "assets" / "icon.png").write_bytes(png(600, 400))
        self.assertFails("is 600x400; needs a square PNG")

    # --- Cursor ---

    def test_cursor_version_drift(self):
        self.edit_json(".cursor-plugin/plugin.json", lambda d: d.update(version="0.0.1"))
        self.assertFails(".cursor-plugin/plugin.json: version differs")

    def test_cursor_logo_cannot_leave_repo(self):
        self.edit_json(".cursor-plugin/plugin.json", lambda d: d.update(logo="../icon.png"))
        self.assertFails("must be relative to the repo with no '..'")

    def test_cursor_mcp_path_must_exist(self):
        self.edit_json(".cursor-plugin/plugin.json", lambda d: d.update(mcpServers="missing.json"))
        self.assertFails("'missing.json' does not exist")

    def test_cursor_wrong_server_url(self):
        self.edit_json("mcp.json", lambda d: d["mcpServers"]["drinkedin-night-out"].update(url="https://ai.drinkedin.net/mcp"))
        self.assertFails("mcp.json: mcpServers.drinkedin-night-out.url must be")

    def test_cursor_unknown_field(self):
        self.edit_json(".cursor-plugin/plugin.json", lambda d: d.update(displayName="X"))
        self.assertFails("unknown field 'displayName'")

    # --- Gemini ---

    def test_gemini_wrong_url(self):
        self.edit_json("gemini-extension.json",
                       lambda d: d["mcpServers"]["drinkedin-night-out"].update(httpUrl="https://example.com/mcp"))
        self.assertFails("gemini-extension.json: mcpServers.drinkedin-night-out.httpUrl must be")

    def test_gemini_trust_rejected(self):
        self.edit_json("gemini-extension.json", lambda d: d["mcpServers"]["drinkedin-night-out"].update(trust=True))
        self.assertFails("'trust' is not supported")

    def test_gemini_numeric_age(self):
        self.edit_json("gemini-extension.json", lambda d: d.update(description=d["description"] + " For 21+ only."))
        self.assertFails("numeric drinking age")

    # --- MCP Registry ---

    def test_registry_description_limit(self):
        self.edit_json("server.json", lambda d: d.update(description="x" * 101))
        self.assertFails("server.json: description must be 1 to 100 characters")

    def test_registry_remote_type(self):
        self.edit_json("server.json", lambda d: d["remotes"][0].update(type="sse"))
        self.assertFails("server.json: remotes must be one streamable-http remote")

    # --- skill and copy rules ---

    def test_skill_name_must_match_folder(self):
        path = self.root / "skills" / "drinkedin-night-out" / "SKILL.md"
        path.write_text(path.read_text().replace("name: drinkedin-night-out", "name: night-out", 1))
        self.assertFails("must match its folder")

    def test_skill_metadata_must_be_strings(self):
        path = self.root / "skills" / "drinkedin-night-out" / "SKILL.md"
        path.write_text(path.read_text().replace("metadata:\n", "metadata:\n  pricing:\n", 1))
        self.assertFails("metadata must map strings to strings")

    def test_skill_deep_nesting_rejected(self):
        path = self.root / "skills" / "drinkedin-night-out" / "SKILL.md"
        path.write_text(path.read_text().replace("metadata:\n", "metadata:\n  drinkedin:\n    pricing: free\n", 1))
        self.assertFails("nesting deeper than one level")

    def test_skill_numeric_age(self):
        path = self.root / "skills" / "drinkedin-night-out" / "SKILL.md"
        path.write_text(path.read_text() + "\nOnly for people aged 21 and over.\n")
        self.assertFails("SKILL.md: contains a numeric drinking age")

    def test_readme_other_server_link(self):
        path = self.root / "README.md"
        path.write_text(path.read_text() + "\nAlso see https://ai.drinkedin.net/mcp for paid tools.\n")
        self.assertFails("README.md: contains a link to the other DrinkedIn MCP server")

    def test_manifest_payment_word(self):
        self.edit_json(".claude-plugin/plugin.json", lambda d: d.update(description=d["description"] + " Pay with USDC."))
        self.assertFails("payment word")

    # --- OpenAI (only when openai/ exists) ---

    def make_openai(self, script="def main(argv):\n    return 0\n"):
        pkg = self.root / "openai"
        (pkg / "scripts").mkdir(parents=True)
        (pkg / "scripts" / "validate.py").write_text(script)
        (pkg / "plugin.json").write_text('{"name": "drinkedin-night-out"}')
        (pkg / "mcp.json").write_text(json.dumps({"mcpServers": {"n": {"url": validate.MCP_URL}}}))
        return pkg

    def test_openai_validator_failure_propagates(self):
        self.make_openai("def main(argv):\n    print('ERROR bad')\n    return 1\n")
        self.assertFails("openai/scripts/validate.py failed")

    def test_openai_stale_zip(self):
        pkg = self.make_openai()
        (pkg / "dist").mkdir()
        with zipfile.ZipFile(pkg / "dist" / "drinkedin-night-out-openai.zip", "w") as zf:
            zf.writestr("plugin.json", '{"name": "old"}')
            zf.writestr("mcp.json", (pkg / "mcp.json").read_text())
        self.assertFails("plugin.json differs from openai/plugin.json (stale ZIP")

    def test_openai_zip_extra_entry(self):
        pkg = self.make_openai()
        (pkg / "dist").mkdir()
        with zipfile.ZipFile(pkg / "dist" / "x.zip", "w") as zf:
            zf.writestr("plugin.json", (pkg / "plugin.json").read_text())
            zf.writestr("mcp.json", (pkg / "mcp.json").read_text())
            zf.writestr("scripts/validate.py", "")
        self.assertFails("unexpected entry 'scripts/validate.py'")

    def test_openai_ok_when_valid(self):
        self.make_openai()
        self.assertEqual(self.errors(), [])


if __name__ == "__main__":
    unittest.main()
