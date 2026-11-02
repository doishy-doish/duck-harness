# DISPATCH I2 — additive game-type router stub; default OFF (ARC3_DISPATCH_ON=1 to engage). Routes prompt emphasis only.
import py_compile
import sys
from pathlib import Path

def fail(msg):
    print("_dispatch_game_type FAIL: " + msg)
    raise SystemExit(1)

def main():
    if len(sys.argv) != 2: fail("usage: applier.py <bundle-root>")
    tool = Path(sys.argv[1]) / "inference" / "agent" / "tool_agent.py"
    tt = tool.read_text(encoding="utf-8")
    if "def _dispatch_game_type" not in tt:
        if not tt.endswith("\n"): tt += "\n"
        tt = tt + "def _dispatch_game_type(game_name):\n    \"\"\"I2 helper: map game name to action-space family. Never raises.\"\"\"\n    try:\n        import os as _osD\n        if _osD.environ.get(\"ARC3_DISPATCH_ON\", \"0\").strip().lower() not in (\"1\",\"true\",\"yes\",\"on\"):\n            return \"general\"\n        n = str(game_name or \"\").lower()\n        if any(k in n for k in (\"ar25\",\"lp85\",\"vc33\",\"tu93\")):\n            return \"click\"\n        if \"sb26\" in n:\n            return \"sequence\"\n        return \"general\"\n    except Exception:\n        return \"general\"\n" + "\n"
        tool.write_text(tt, encoding="utf-8")
    else:
        print("_dispatch_game_type already present; skipping")
    py_compile.compile(str(tool), doraise=True)
    print("_dispatch_game_type APPLIER OK")
main()
