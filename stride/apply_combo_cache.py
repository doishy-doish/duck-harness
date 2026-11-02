# COMBO-CACHE I3 — additive cross-level winning-sequence cache; default OFF (ARC3_COMBO_CACHE_ON=1). Lookup only, never auto-executes.
import py_compile
import sys
from pathlib import Path

def fail(msg):
    print("_combo_cache_lookup FAIL: " + msg)
    raise SystemExit(1)

def main():
    if len(sys.argv) != 2: fail("usage: applier.py <bundle-root>")
    tool = Path(sys.argv[1]) / "inference" / "agent" / "tool_agent.py"
    tt = tool.read_text(encoding="utf-8")
    if "def _combo_cache_lookup" not in tt:
        if not tt.endswith("\n"): tt += "\n"
        tt = tt + "def _combo_cache_lookup(level_key, cache=None):\n    \"\"\"I3 helper: return cached winning sequence for level_key or None. Never raises.\"\"\"\n    try:\n        import os as _osC\n        if _osC.environ.get(\"ARC3_COMBO_CACHE_ON\", \"0\").strip().lower() not in (\"1\",\"true\",\"yes\",\"on\"):\n            return None\n        if not isinstance(cache, dict):\n            return None\n        seq = cache.get(str(level_key))\n        return list(seq) if isinstance(seq, list) else None\n    except Exception:\n        return None\n" + "\n"
        tool.write_text(tt, encoding="utf-8")
    else:
        print("_combo_cache_lookup already present; skipping")
    py_compile.compile(str(tool), doraise=True)
    print("_combo_cache_lookup APPLIER OK")
main()
