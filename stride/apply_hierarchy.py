# apply_hierarchy.py — subgoal controller add-on (ReAcTree adaptation, ~120 lines runtime).
# Base: v25 banked bits. Standalone (no Hail Mary dependency); composes when present.
# Line-oriented replace-or-throw: short escape-free needles, insert after matched LINE,
# assert exactly 1 hit or abort. Idempotent, py_compile-guarded.
# Hunks: (1) P3 subgoal prompt after MOUSE line; (2) controller helper before
# _build_user_message; (3) per-step SG injection in _build_user_message tail is DONE
# by the caller hunk (4) level-transition control block after ELIF needle.
# Fail-closed everywhere: no SG lines -> controller returns "" / skips.
# No quit-words in any emitted string (give_up/abandon/quit/stop-word filtered).
# Usage: python3 apply_hierarchy.py /path/to/ARC3-Inference
import py_compile
import sys
from pathlib import Path

P3 = "    \"- At the start of each level, name 2-4 subgoals as SG: <short text> lines plus FOCUS: <n> (which subgoal you pursue first). Short, concrete, ordered (e.g. SG: map the exits). One line per subgoal.\\n\""

MOUSE_NEEDLE = "For `MOUSE`, pass"
ELIF_NEEDLE = 'elif previous_step_summary.get("level_transition"):'
HELPER_DEF_ANCHOR = "    def _build_user_message("

SG_HELPER = '''_HAILMARY_SG_BUDGETS_CACHE = None


def _hailmary_sg_parse(agent, text):
    """Store verbatim SG lines from model output. Opaque strings, no semantics."""
    try:
        sgs = []
        for _ln in str(text or "").splitlines():
            _s = _ln.strip()
            if _s.upper().startswith("SG:") and len(_s) > 4:
                sgs.append({"text": _s[3:].strip()[:160], "stalls": 0, "budget": 0})
                if len(sgs) >= 4:
                    break
        if sgs:
            try:
                import json as _json2
                import os as _os2
                _bp = _os2.environ.get("ARC3_HAILMARY_BASELINES", "").strip()
                _lv = int(getattr(agent, "_hailmary_level_seen", 1) or 1)
                _par = 0.0
                if _bp:
                    _t = _json2.load(open(_bp, "r", encoding="utf-8"))
                    _stem = str(getattr(agent, "_hailmary_run_stem", "") or "")
                    for _k in sorted(_t.keys(), key=len, reverse=True):
                        if _k and _k in _stem:
                            _pars = _t.get(_k, [])
                            if isinstance(_pars, list) and 1 <= _lv <= len(_pars):
                                _par = float(_pars[_lv - 1])
                            break
                _each = (_par / len(sgs)) if _par > 0 else 0.0
            except Exception:
                _each = 0.0
            for _g in sgs:
                _g["budget"] = _each
            agent._hailmary_subgoals = sgs
            agent._hailmary_sg_idx = 0
    except Exception:
        pass


def _hailmary_sg_line(agent):
    """One-line current-subgoal injection. '' when inactive."""
    try:
        _sgs = list(getattr(agent, "_hailmary_subgoals", []) or [])
        if not _sgs:
            return ""
        _i = int(getattr(agent, "_hailmary_sg_idx", 0) or 0) % len(_sgs)
        _g = _sgs[_i]
        _msg = ("Current subgoal (%d/%d): %s. Subgoal stall count %d."
                % (_i + 1, len(_sgs), _g.get("text", ""), int(_g.get("stalls", 0) or 0)))
        _low = _msg.lower()
        for _w in ("give_up", "abandon", "quit"):
            if _w in _low:
                return ""
        if " stop " in (" " + _low + " "):
            return ""
        return _msg
    except Exception:
        return ""
'''

SG_CALL = '''                try:
                    _sgs = list(getattr(self, "_hailmary_subgoals", []) or [])
                    if _sgs:
                        _i = int(getattr(self, "_hailmary_sg_idx", 0) or 0) % len(_sgs)
                        _g = _sgs[_i]
                        _g["stalls"] = int(_g.get("stalls", 0) or 0) + 1
                        _b = float(_g.get("budget", 0) or 0)
                        if _b > 0 and _g["stalls"] > _b:
                            try:
                                _note = "SG '%s' stalled after %d actions" % (_g.get("text", "")[:80], _g["stalls"])
                                _pb = getattr(self, "_hailmary_playbook_mem", None)
                                if isinstance(_pb, list):
                                    _pb.append(_note)
                            except Exception:
                                pass
                            self._hailmary_sg_idx = (_i + 1) % len(_sgs)
                            self._hailmary_subgoals[_i]["stalls"] = 0
                            if self._hailmary_sg_idx == 0:
                                self._hailmary_subgoals = []
                except Exception:
                    pass'''


def fail(msg):
    print("HIERARCHY APPLIER FAIL: " + msg)
    raise SystemExit(1)


def insert_after_line(text, needle, new_lines, expect, tag):
    idx = [i for i, l in enumerate(text.split("\n")) if needle in l]
    if len(idx) != expect:
        fail("%s: needle %r found %d times, want %d" % (tag, needle[:60], len(idx), expect))
    lines = text.split("\n")
    pos = idx[0]
    return "\n".join(lines[:pos + 1] + new_lines + lines[pos + 1:])


def main():
    if len(sys.argv) != 2:
        fail("usage: python3 apply_hierarchy.py /path/to/ARC3-Inference")
    root = Path(sys.argv[1])
    prompts = root / "inference" / "agent" / "prompts.py"
    tool = root / "inference" / "agent" / "tool_agent.py"
    pt = prompts.read_text(encoding="utf-8")
    tt = tool.read_text(encoding="utf-8")
    if "SG: <short text>" not in pt:
        pt = insert_after_line(pt, MOUSE_NEEDLE, [P3], 1, "prompts-p3")
        prompts.write_text(pt, encoding="utf-8")
    else:
        print("P3 already present; skipping prompts hunk")
    if "_hailmary_sg_line" not in tt:
        tt = insert_after_line(tt, HELPER_DEF_ANCHOR, SG_HELPER.split("\n"), 1, "tool-sghelper")
        tt = insert_after_line(tt, ELIF_NEEDLE, SG_CALL.split("\n"), 1, "tool-sgcall")
        tool.write_text(tt, encoding="utf-8")
    else:
        print("SG controller already present; skipping tool hunks")
    for f in (prompts, tool):
        py_compile.compile(str(f), doraise=True)
    print("HIERARCHY APPLIER OK")


main()
