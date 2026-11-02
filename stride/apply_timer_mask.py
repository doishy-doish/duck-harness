# TIMER-MASK I1 — additive env-gated rows0-61 + border helper; default OFF (no behavior change unless ARC3_TIMER_MASK_ON=1).
import py_compile
import sys
from pathlib import Path

def fail(msg):
    print("_timer_mask_core FAIL: " + msg)
    raise SystemExit(1)

def main():
    if len(sys.argv) != 2: fail("usage: applier.py <bundle-root>")
    tool = Path(sys.argv[1]) / "inference" / "agent" / "tool_agent.py"
    tt = tool.read_text(encoding="utf-8")
    if "def _timer_mask_core" not in tt:
        if not tt.endswith("\n"): tt += "\n"
        tt = tt + "def _timer_mask_core(grid, border=0, max_rows=61):\n    \"\"\"I1 helper: crop HUD border + cap timer-bar rows. Env-gated by caller. Never raises.\"\"\"\n    try:\n        import os as _osM\n        if _osM.environ.get(\"ARC3_TIMER_MASK_ON\", \"0\").strip().lower() not in (\"1\",\"true\",\"yes\",\"on\"):\n            return grid\n        b = max(0, int(_osM.environ.get(\"ARC3_STATE_IDENTITY_BORDER\", str(border))))\n        rows = grid[:max_rows] if len(grid) > max_rows else grid\n        if b <= 0:\n            return rows\n        cols = max((len(r) for r in rows), default=0)\n        if len(rows) > 2*b and cols > 2*b:\n            return [list(r[b:cols-b]) for r in rows[b:len(rows)-b]]\n        return rows\n    except Exception:\n        return grid\n" + "\n"
        tool.write_text(tt, encoding="utf-8")
    else:
        print("_timer_mask_core already present; skipping")
    py_compile.compile(str(tool), doraise=True)
    print("_timer_mask_core APPLIER OK")
main()
