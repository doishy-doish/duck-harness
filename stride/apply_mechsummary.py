# apply_mechsummary.py — mechanical summary swap (Compact-Bench adaptation, ~45 lines).
# Source: Compact-Bench, arXiv:2610.31710 — VERIFIED firsthand
# (scratch/search/verify-compactbench-2610-31710.html): LLM summaries retain at most
# 16.0% of recurring details vs 79.1% for mechanical extraction; 5-64% of 22
# successes damaged across 14 summarizer backbones. Model-agnostic: deterministic
# extraction of last-12 history items + action-id histogram replaces the LLM
# rolling-summary call when ARC3_MECH_SUMMARY=1. Transfer: coding agents -> ARC-3
# is mechanism-direct (same failure: compaction erases progress state); effect on
# ARC-3 UNMEASURED, demo prices it (token savings measurable immediately).
# Hook: gate at top of _maybe_append_rolling_summary body (anchor verified 1x on
# patched-35.35 real bytes 2026-11-01) + helper before _build_user_message (1x).
# append_transcript(section, text) two-arg form mirrors the method tail.
# Line-oriented replace-or-throw, idempotent, py_compile-guarded.
# Usage: python3 apply_mechsummary.py /path/to/ARC3-Inference
import py_compile
import sys
from pathlib import Path

HELPER_DEF_ANCHOR = "    def _build_user_message("
INTERVAL_ANCHOR = "        interval = _summary_interval_tokens()"

MECH_HELPER = '''def _hailmary_mechanical_text(agent):
    """Deterministic history extraction. No model, no tokens."""
    try:
        import re as _re2
        _hist = list(getattr(agent, "_history_messages", []) or [])[-12:]
        _lines = []
        _freq = {}
        for _m in _hist:
            try:
                _s = str(_m)[:220].replace("\\n", " | ")
            except Exception:
                _s = "?"
            for _a in _re2.findall(r"ACTION[0-9]", _s):
                _freq[_a] = _freq.get(_a, 0) + 1
            _lines.append(_s)
        _hist_line = "last12=" + str(len(_hist))
        _act_line = "actions=" + ",".join("%s:%d" % (_k, _freq[_k]) for _k in sorted(_freq)) if _freq else "actions=none"
        return "MECHANICAL SUMMARY\\n" + _hist_line + " " + _act_line + "\\n" + "\\n".join(_lines)
    except Exception:
        return "MECHANICAL SUMMARY (unavailable)"
'''

MECH_GATE = '''        try:
            import os as _os5
            if _os5.environ.get("ARC3_MECH_SUMMARY", "").strip().lower() in ("1", "true", "yes", "on"):
                try:
                    append_transcript("ROLLING SUMMARY MECHANICAL", _hailmary_mechanical_text(self))
                except Exception:
                    pass
                return
        except Exception:
            pass'''


def fail(msg):
    print("MECHSUMMARY APPLIER FAIL: " + msg)
    raise SystemExit(1)


def insert_after_line(text, needle, new_lines, expect, tag):
    idx = [i for i, l in enumerate(text.split("\n")) if needle in l]
    if len(idx) != expect:
        fail("%s: needle %r found %d times, want %d" % (tag, needle[:60], len(idx), expect))
    lines = text.split("\n")
    pos = idx[0]
    return "\n".join(lines[:pos + 1] + new_lines + lines[pos + 1:])


def insert_before_line(text, needle, new_lines, expect, tag):
    idx = [i for i, l in enumerate(text.split("\n")) if needle in l]
    if len(idx) != expect:
        fail("%s: needle %r found %d times, want %d" % (tag, needle[:60], len(idx), expect))
    lines = text.split("\n")
    pos = idx[0]
    return "\n".join(lines[:pos] + new_lines + lines[pos:])


def main():
    if len(sys.argv) != 2:
        fail("usage: python3 apply_mechsummary.py /path/to/ARC3-Inference")
    root = Path(sys.argv[1])
    tool = root / "inference" / "agent" / "tool_agent.py"
    tt = tool.read_text(encoding="utf-8")
    if "_hailmary_mechanical_text" not in tt:
        tt = insert_after_line(tt, HELPER_DEF_ANCHOR, MECH_HELPER.split("\n"), 1, "tool-mechhelper")
        tt = insert_before_line(tt, INTERVAL_ANCHOR, MECH_GATE.split("\n"), 1, "tool-mechgate")
        tool.write_text(tt, encoding="utf-8")
    else:
        print("MECHSUMMARY already present; skipping tool hunks")
    py_compile.compile(str(tool), doraise=True)
    print("MECHSUMMARY APPLIER OK")


main()
