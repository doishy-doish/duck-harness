# apply_abstention.py — harness-forced abstention (mechanism-class only, ~40 lines).
# No paper (honestly paperless): deterministic checks first, model only where they
# abstain. Stateless forced-rotation line from history_entries tail: N identical
# action classes with no level change -> one line forcing a different class.
# True call-skipping needs the tool loop; this staged form is the deterministic
# rotation line (refusal-record type, fail-logged: max-2-refusals valve lives in
# the gate spec, not here). Reuses no new state; history_entries already in scope
# at the anchor. Fail-closed everywhere (any exception -> "").
# Base: patched-35.35 lineage (anchors verified 1x on real bytes 2026-11-01) AND
# public 89KB stock file (same anchors 1x: helper-def, same-level line).
# Line-oriented replace-or-throw, idempotent, py_compile-guarded.
# Usage: python3 apply_abstention.py /path/to/ARC3-Inference
import py_compile
import sys
from pathlib import Path

HELPER_DEF_ANCHOR = "    def _build_user_message("
SAME_LEVEL_ANCHOR = 'lines.append("You are still on the same level.")'

ABSTAIN_HELPER = '''def _hailmary_abstain_line(history_entries):
    """Forced-rotation line on N identical tail actions. '' otherwise."""
    try:
        import os as _os6
        if _os6.environ.get("ARC3_ABSTAIN_ON", "").strip().lower() not in ("1", "true", "yes", "on"):
            return ""
        try:
            _n = int(_os6.environ.get("ARC3_ABSTAIN_REPEATS", "6") or 6)
        except Exception:
            _n = 6
        if _n < 2:
            return ""
        _acts = []
        for _e in list(history_entries or [])[-12:]:
            try:
                _a = getattr(_e, "action", None)
                _acts.append(str((_a.get("id") if isinstance(_a, dict) else _a) or "?"))
            except Exception:
                _acts.append("?")
        if len(_acts) < _n:
            return ""
        _tail = _acts[-_n:]
        if len(set(_tail)) == 1 and _tail[0] not in ("?", "none", ""):
            _msg = ("You have repeated %s %d times with no level change. Name a different action class and take one action from it."
                    % (_tail[0], _n))
            _low = _msg.lower()
            for _w in ("give_up", "abandon", "quit"):
                if _w in _low:
                    return ""
            if " stop " in (" " + _low + " "):
                return ""
            return _msg
        return ""
    except Exception:
        return ""
'''

ABSTAIN_CALL = '''                try:
                    _abstain_line = _hailmary_abstain_line(history_entries)
                except Exception:
                    _abstain_line = ""
                if _abstain_line:
                    lines.append(_abstain_line)'''


def fail(msg):
    print("ABSTENTION APPLIER FAIL: " + msg)
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
        fail("usage: python3 apply_abstention.py /path/to/ARC3-Inference")
    root = Path(sys.argv[1])
    tool = root / "inference" / "agent" / "tool_agent.py"
    tt = tool.read_text(encoding="utf-8")
    if "_hailmary_abstain_line" not in tt:
        assert_anchor_once(tt, HELPER_DEF_ANCHOR, 1, "tool-abstainhelper")
        tt = insert_after_line(tt, SAME_LEVEL_ANCHOR, ABSTAIN_CALL.split("\n"), 1, "tool-abstaincall")
        if not tt.endswith("\n"):
            tt += "\n"
        tt = tt + ABSTAIN_HELPER + "\n"
        tool.write_text(tt, encoding="utf-8")
    else:
        print("ABSTENTION already present; skipping tool hunks")
    py_compile.compile(str(tool), doraise=True)
    print("ABSTENTION APPLIER OK")


main()
