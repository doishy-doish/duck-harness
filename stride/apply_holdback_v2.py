# HOLDBACK-v2 — modelability trigger (entry 786 verified safe window offline).
# Fires: level_not_cleared AND think_toks_this_level >= T AND acts_this_level <= A_min.
# Verified: (acts==0, toks>=70) -> 10/24 failed levels fire, 0 cleared killed (cleared => acts>0 structurally).
# Blind act-caps KILLED by same data (H=100 murders re86-L5's scored 131).
# Env-gated OFF by default. Threshold units: raw tokens; default 7000 ~= v27 T=70 (per-level seconds ~= hundreds of tokens).
# LIMIT (documented): v1 hooks _action_guard_hook (proposal site). Pure no-propose deliberation (model thinks,
# never proposes) needs the analyzer-loop hook (v2). v1 catches high-think-before-first-proposal + runaway
# re-proposal on uncleared levels.
import py_compile
import sys
from pathlib import Path


def fail(msg):
    print("_holdback_v2 FAIL: " + msg)
    raise SystemExit(1)


CORE = '''
def _holdback_v2_enabled() -> bool:
    """Modelability hold-back (entry 786). Env-gated, default OFF."""
    try:
        import os as _osH
        return _osH.environ.get("ARC3_HOLDBACK_V2_ON", "0").strip().lower() in ("1", "true", "yes", "on")
    except Exception:
        return False


def _holdback_v2_params() -> tuple:
    """(min_acts, think_toks). Defaults = verified safe window (786)."""
    try:
        import os as _osH
        a = int(_osH.environ.get("ARC3_HOLDBACK_V2_MIN_ACTS", "0") or 0)
        t = int(_osH.environ.get("ARC3_HOLDBACK_V2_TOKENS", "7000") or 7000)
        return (max(0, a), max(1, t))
    except Exception:
        return (0, 7000)


def _holdback_v2_state(agent) -> dict:
    st = getattr(agent, "_holdback_v2", None)
    if not isinstance(st, dict):
        st = {"level": None, "proposals": 0, "think_base": 0}
        try:
            agent._holdback_v2 = st
        except Exception:
            pass
    return st


def _holdback_v2_note(agent, level) -> None:
    """Count one proposed action on this level; reset on level change. Never raises."""
    try:
        if not _holdback_v2_enabled():
            return
        st = _holdback_v2_state(agent)
        if st.get("level") != level:
            st["level"] = level
            st["proposals"] = 0
            try:
                st["think_base"] = int(getattr(agent, "_summary_context_tokens_since_attempt", 0) or 0)
            except Exception:
                st["think_base"] = 0
        st["proposals"] = int(st.get("proposals", 0) or 0) + 1
    except Exception:
        pass


def _holdback_v2_check(agent, level):
    """(fire, detail). Pure decision core; verified offline (entry 786). Never raises."""
    try:
        if not _holdback_v2_enabled():
            return (False, "")
        st = _holdback_v2_state(agent)
        if st.get("level") != level:
            return (False, "")
        min_acts, tok_t = _holdback_v2_params()
        acts = int(st.get("proposals", 0) or 0)
        try:
            cur = int(getattr(agent, "_summary_context_tokens_since_attempt", 0) or 0)
        except Exception:
            cur = 0
        think = cur - int(st.get("think_base", 0) or 0)
        if acts <= min_acts and think >= tok_t:
            return (True, "holdback-v2: %d proposed acts and ~%d deliberation tokens on uncleared level %s with no model; act on the board now (move/click a salient target) instead of further deliberation." % (acts, think, level))
        return (False, "")
    except Exception:
        return (False, "")
'''


def main():
    if len(sys.argv) != 2:
        fail("usage: apply_holdback_v2.py <bundle-root>")
    tool = Path(sys.argv[1]) / "inference" / "agent" / "tool_agent.py"
    tt = tool.read_text(encoding="utf-8")
    if "_holdback_v2_check" not in tt:
        if not tt.endswith("\n"):
            tt += "\n"
        tt = tt + CORE + "\n"
    anchor = "        guard.note_level(level)\n        # the solver passes ENGINE names"
    if "_holdback_v2_note(self, level)" not in tt:
        if anchor not in tt:
            fail("anchor not found (harness drifted); aborting, no changes made")
        tt = tt.replace(
            anchor,
            "        guard.note_level(level)\n"
            "        _holdback_v2_note(self, level)\n"
            "        _hb_fire, _hb_detail = _holdback_v2_check(self, level)\n"
            "        if _hb_fire:\n"
            '            return ("holdback_v2", _hb_detail)\n'
            "        # the solver passes ENGINE names",
            1,
        )
        tool.write_text(tt, encoding="utf-8")
    else:
        print("_holdback_v2 hook already present; skipping")
    py_compile.compile(str(tool), doraise=True)
    print("_holdback_v2 APPLIER OK")


main()
