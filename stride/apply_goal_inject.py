# apply_goal_inject.py — harness-side progress-state injection + regression refusal (entry 803).
# Acting-class: the HARNESS maintains a monotonic reached-record parsed from
# prompt-visible history; the model never maintains state. Injection proved at
# 3B (injected arm step4=1/2, base 0/2, run 41411527978).
# v1 limits (documented): plan/pos parsed from outgoing prompt history text
# (no analyzer-side text anchor verified); refusal is keyword-level and
# conservative (entity must be named in the proposal) — fail-closed by design.
# Anchors verified 1x on patched-35.35 real bytes (343899 B):
#   prompts "For `MOUSE`, pass", tool retained_function_context line,
#   tool "self._noop_guard_pre_hash = state_hash".
# Order-independent vs holdback-v2 (disjoint anchors). Env ARC3_GOAL_INJECT_ON.
# Usage: python3 apply_goal_inject.py /path/to/ARC3-Inference
import py_compile
import sys
from pathlib import Path


def fail(msg):
    print("GOAL_INJECT APPLIER FAIL: " + msg)
    raise SystemExit(1)


P_GOAL = "    \"- At the start of each level, state your plan as PLAN lines (1. <verb> <target>) and every turn state AT STEP <k> plus NEXT action. Ordered, concrete, short.\\n\""

P_NEEDLE = "For `MOUSE`, pass"

INJECT_ANCHOR = "user_prompt += self._retained_function_context()"
INJECT_NEW = ("user_prompt += self._retained_function_context()\n"
              "        try:\n"
              "            _glvl = getattr(self, \"_goal_guard_level\", None)\n"
              "            _goal_note_prompt(self, _glvl, user_prompt)\n"
              "            _gb = _goal_inject_block(self, _glvl)\n"
              "        except Exception:\n"
              "            _gb = \"\"\n"
              "        if _gb:\n"
              "            user_prompt += \"\\n\" + _gb")

GUARD_ANCHOR = "self._noop_guard_pre_hash = state_hash"
GUARD_NEW = ("self._noop_guard_pre_hash = state_hash\n"
             "        try:\n"
             "            _ggl = level\n"
             "            if getattr(self, \"_goal_guard_level\", None) != _ggl:\n"
             "                self._goal_guard_level = _ggl\n"
             "                _gst = getattr(self, \"_goal_inject\", None)\n"
             "                if isinstance(_gst, dict) and _gst.get(\"level\") != _ggl:\n"
             "                    _gst[\"level\"] = _ggl\n"
             "                    _gst[\"reached\"] = 0\n"
             "                    _gst[\"plan\"] = []\n"
             "        except Exception:\n"
             "            pass\n"
             "        _gr_fire, _gr_detail = _goal_refuse_check(self, level, action_name, action_data)\n"
             "        if _gr_fire:\n"
             "            return (\"goal_refuse\", _gr_detail)")

MECH_NEEDLE = 'getattr(self, "_h1_switches_this_level", 0)'
MECH_OLD = 'getattr(self, "_h1_switches_this_level", 0))'
MECH_NEW = ('getattr(self, "_h1_switches_this_level", 0))\n'
            '                + " goal_inj=%s goal_ref=%s" % (getattr(self, "_goal_injects_this_level", 0), getattr(self, "_goal_refuses_this_level", 0))')

GOAL_CORE = '''
import re as _reG

_GOAL_VERBS = ("move", "get", "open", "unlock", "go", "exit", "push",
               "collect", "carry", "use", "take", "grab", "click", "press")
_GOAL_ENTS = ("robot", "key", "door", "exit", "button", "box", "target",
              "switch", "lever", "gate", "tile")


def _goal_inject_enabled() -> bool:
    """Env-gated, default OFF."""
    try:
        import os as _osG
        return _osG.environ.get("ARC3_GOAL_INJECT_ON", "0").strip().lower() in ("1", "true", "yes", "on")
    except Exception:
        return False


def _goal_state(agent) -> dict:
    st = getattr(agent, "_goal_inject", None)
    if not isinstance(st, dict):
        st = {"level": None, "reached": 0, "plan": []}
        try:
            agent._goal_inject = st
        except Exception:
            pass
    return st


def _goal_parse_steps(text):
    """Plan steps from numbered lines: [(idx, verb, entity)]. Never raises."""
    out = []
    try:
        for _ln in str(text or "").splitlines():
            _m = _reG.match(r"\\s*(\\d+)[\\).\\:]\\s*(.+)", _ln.strip())
            if not _m:
                continue
            _body = _m.group(2).lower()
            _v = next((v for v in _GOAL_VERBS if v in _body), "")
            _e = next((e for e in _GOAL_ENTS if e in _body), "")
            if _v and _e:
                out.append((int(_m.group(1)), _v, _e))
    except Exception:
        pass
    return out[:6]


def _goal_parse_pos(text):
    """Stated current step number, or None. Never raises."""
    try:
        _m = _reG.search(r"(current|now|at|step)\\D{0,10}(\\d+)", str(text or "").lower())
        if _m:
            return int(_m.group(2))
    except Exception:
        pass
    return None


def _goal_note_prompt(agent, level, prompt_text) -> None:
    """Monotonic reached-record from prompt-visible history. Never raises."""
    try:
        if not _goal_inject_enabled():
            return
        st = _goal_state(agent)
        if st.get("level") != level:
            st["level"] = level
            st["reached"] = 0
            st["plan"] = []
        _steps = _goal_parse_steps(prompt_text)
        if _steps:
            if not st.get("plan"):
                st["plan"] = _steps
            elif [s[:2] for s in st["plan"]] != [s[:2] for s in _steps]:
                # new plan seen (e.g. level transition before first guard):
                # reset, adopt latest
                st["plan"] = _steps
                st["reached"] = 0
        _pos = _goal_parse_pos(prompt_text)
        if _pos and _pos > int(st.get("reached", 0) or 0):
            st["reached"] = min(_pos - 1, 6)
        try:
            agent._goal_inject = st
        except Exception:
            pass
    except Exception:
        pass


def _goal_inject_block(agent, level):
    """Authoritative progress block for the prompt. '' when off/unknown."""
    try:
        if not _goal_inject_enabled():
            return ""
        st = _goal_state(agent)
        if st.get("level") != level:
            return ""
        _r = int(st.get("reached", 0) or 0)
        if _r <= 0:
            return ""
        try:
            agent._goal_injects_this_level = int(getattr(agent, "_goal_injects_this_level", 0) or 0) + 1
        except Exception:
            pass
        return ("HARNESS RECORD (authoritative, overrides memory): steps 1-%d COMPLETE. "
                "You are past step %d. Do NOT repeat completed steps. State AT STEP and NEXT action."
                % (_r, _r))
    except Exception:
        return ""


def _goal_refuse_check(agent, level, action_name, action_data):
    """Tripwire: refuse proposals matching a completed step. Never raises."""
    try:
        if not _goal_inject_enabled():
            return (False, "")
        st = _goal_state(agent)
        if st.get("level") != level:
            return (False, "")
        _r = int(st.get("reached", 0) or 0)
        if _r <= 0:
            return (False, "")
        _prop = (str(action_name or "") + " " + str(action_data or "")).lower()
        for (_i, _v, _e) in (st.get("plan") or []):
            if _i <= _r and len(_e) >= 3 and _v in _prop and _e in _prop:
                try:
                    agent._goal_refuses_this_level = int(getattr(agent, "_goal_refuses_this_level", 0) or 0) + 1
                except Exception:
                    pass
                return (True, "goal_refuse: repeats completed step %d; act on the NEXT uncompleted step instead." % _i)
        return (False, "")
    except Exception:
        return (False, "")
'''


def replace_or_throw(text, anchor, new, label):
    count = text.count(anchor)
    if new in text and count == 0:
        return text, "%s: already applied (skip)" % label
    if count != 1:
        fail("anchor for %s found %dx (want 1)" % (label, count))
    return text.replace(anchor, new, 1), "%s: applied" % label


def insert_after_line(text, needle, new_lines, expect, tag):
    idx = [i for i, l in enumerate(text.split("\n")) if needle in l]
    if len(idx) != expect:
        fail("%s: needle %r found %d times, want %d" % (tag, needle[:60], len(idx), expect))
    lines = text.split("\n")
    pos = idx[0]
    return "\n".join(lines[:pos + 1] + new_lines + lines[pos + 1:])


def main():
    if len(sys.argv) != 2:
        fail("usage: python3 apply_goal_inject.py /path/to/ARC3-Inference")
    root = Path(sys.argv[1])
    prompts = root / "inference" / "agent" / "prompts.py"
    tool = root / "inference" / "agent" / "tool_agent.py"
    pt = prompts.read_text(encoding="utf-8")
    tt = tool.read_text(encoding="utf-8")
    if "AT STEP <k>" not in pt:
        pt = insert_after_line(pt, P_NEEDLE, [P_GOAL], 1, "prompts-goal")
        prompts.write_text(pt, encoding="utf-8")
        print("prompts-goal: applied")
    else:
        print("prompts-goal: already applied (skip)")
    if "_goal_refuse_check" not in tt:
        tt, r1 = replace_or_throw(tt, INJECT_ANCHOR, INJECT_NEW, "inject-call")
        print("  " + r1)
        tt, r2 = replace_or_throw(tt, GUARD_ANCHOR, GUARD_NEW, "guard-refuse")
        print("  " + r2)
        if not tt.endswith("\n"):
            tt += "\n"
        tt = tt + GOAL_CORE + "\n"
        tool.write_text(tt, encoding="utf-8")
    else:
        print("tool goal hook: already applied (skip)")
    # optional LEVEL_MECH counter surface (self-reveal); skip silently if absent
    tt2 = tool.read_text(encoding="utf-8")
    if MECH_NEEDLE in tt2 and "goal_ref=" not in tt2 and tt2.count(MECH_OLD) == 1:
        tt2 = tt2.replace(MECH_OLD, MECH_NEW, 1)
        tool.write_text(tt2, encoding="utf-8")
        print("level-mech goal counters: applied")
    else:
        print("level-mech goal counters: skipped (absent or already present)")
    for f in (prompts, tool):
        try:
            py_compile.compile(str(f), doraise=True)
        except Exception as exc:
            fail("%s does not compile (%r)" % (f.name, exc,))
    print("GOAL_INJECT APPLIER OK")


main()
