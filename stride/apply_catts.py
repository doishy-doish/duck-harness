# apply_catts.py — vote-uncertainty adaptive compute (CATTS adaptation, ~45 lines runtime).
# Source: CATTS, arXiv:2602.12276 — VERIFIED firsthand
# (scratch/search/verify-catts-2602-12276.html): vote-derived uncertainty (entropy,
# top-1/top-2 margin) allocates compute only to contentious decisions; +11.8% over
# majority voting with fewer tokens (WebArena-Lite/Mind2Web/GoBrowse). Transfer:
# task-family inference (web agents -> ARC-3); effect on ARC-3 UNMEASURED, demo prices it.
# Mechanism: per-turn entropy over last-8 action classes from history_entries (already
# in scope at the anchor); contentious -> one arbiter line (model adjudicates between
# the top-2 candidate classes); consensus -> "" (zero tokens). Fail-closed everywhere.
# Base: patched-35.35 lineage (anchors verified 1x on real bytes 2026-11-01).
# Line-oriented replace-or-throw, idempotent, py_compile-guarded.
# Usage: python3 apply_catts.py /path/to/ARC3-Inference
import py_compile
import sys
from pathlib import Path

P4 = "    \"- When two continuations disagree, adjudicate before acting: say which candidate you keep and why, in one line. When they agree, act without commentary.\\n\""

MOUSE_NEEDLE = "For `MOUSE`, pass"
HELPER_DEF_ANCHOR = "    def _build_user_message("
CODEEXEC_ANCHOR = 'lines.append(f"The code executed {normalized} {label} in the previous sequence.")'

CATTS_HELPER = '''def _hailmary_catts_line(history_entries):
    """Arbiter line only for contentious decisions. '' on consensus/unknown."""
    try:
        import math as _math
        import os as _os4
        if _os4.environ.get("ARC3_CATTS_ON", "").strip().lower() not in ("1", "true", "yes", "on"):
            return ""
        try:
            _ent = float(_os4.environ.get("ARC3_CATTS_ENT", "1.0") or 1.0)
        except Exception:
            _ent = 1.0
        _acts = []
        for _e in list(history_entries or [])[-8:]:
            try:
                _a = getattr(_e, "action", None)
                _acts.append(str((_a.get("id") if isinstance(_a, dict) else _a) or "?"))
            except Exception:
                _acts.append("?")
        if len(_acts) < 4:
            return ""
        _freq = {}
        for _a in _acts:
            _freq[_a] = _freq.get(_a, 0) + 1
        _n = float(len(_acts))
        _h = -sum((_f / _n) * _math.log(_f / _n + 1e-9) for _f in _freq.values())
        _top = sorted(_freq.values(), reverse=True)
        _margin = ((_top[0] - _top[1]) / _n) if len(_top) > 1 else 1.0
        if _h < _ent and _margin >= 0.5:
            return ""
        _cands = sorted(_freq, key=lambda _k: -_freq[_k])[:2]
        _msg = ("Contentious decision: recent actions split %s. Adjudicate in one line (keep one, drop the other), then act."
                % ("/".join(_cands),))
        _low = _msg.lower()
        for _w in ("give_up", "abandon", "quit"):
            if _w in _low:
                return ""
        return _msg
    except Exception:
        return ""
'''

CATTS_CALL = '''                try:
                    _catts_line = _hailmary_catts_line(history_entries)
                except Exception:
                    _catts_line = ""
                if _catts_line:
                    lines.append(_catts_line)'''


def fail(msg):
    print("CATTS APPLIER FAIL: " + msg)
    raise SystemExit(1)


def insert_after_line(text, needle, new_lines, expect, tag):
    idx = [i for i, l in enumerate(text.split("\n")) if needle in l]
    if len(idx) != expect:
        fail("%s: needle %r found %d times, want %d" % (tag, needle[:60], len(idx), expect))
    lines = text.split("\n")
    pos = idx[0]
    return "\n".join(lines[:pos + 1] + new_lines + lines[pos + 1:])


def assert_anchor_once(text, needle, expect, tag):
    # File-identity check only: proves we are in the right file. Module-level
    # helpers are APPENDED at EOF (never inserted after a `def` line — that
    # breaks the suite: IndentationError, caught by GH verify-stride 2026-11-01).
    idx = [i for i, l in enumerate(text.split("\n")) if needle in l]
    if len(idx) != expect:
        fail("%s: needle %r found %d times, want %d" % (tag, needle[:60], len(idx), expect))


def main():
    if len(sys.argv) != 2:
        fail("usage: python3 apply_catts.py /path/to/ARC3-Inference")
    root = Path(sys.argv[1])
    prompts = root / "inference" / "agent" / "prompts.py"
    tool = root / "inference" / "agent" / "tool_agent.py"
    pt = prompts.read_text(encoding="utf-8")
    tt = tool.read_text(encoding="utf-8")
    if "adjudicate before acting" not in pt:
        pt = insert_after_line(pt, MOUSE_NEEDLE, [P4], 1, "prompts-p4")
        prompts.write_text(pt, encoding="utf-8")
    else:
        print("P4 already present; skipping prompts hunk")
    if "_hailmary_catts_line" not in tt:
        assert_anchor_once(tt, HELPER_DEF_ANCHOR, 1, "tool-cattshelper")
        tt = insert_after_line(tt, CODEEXEC_ANCHOR, CATTS_CALL.split("\n"), 1, "tool-cattscall")
        if not tt.endswith("\n"):
            tt += "\n"
        tt = tt + CATTS_HELPER + "\n"
        tool.write_text(tt, encoding="utf-8")
    else:
        print("CATTS already present; skipping tool hunks")
    for f in (prompts, tool):
        py_compile.compile(str(f), doraise=True)
    print("CATTS APPLIER OK")


main()
