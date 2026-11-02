# apply_prose_parse.py — unified harness-side prose parser (entry 812; reviewer's "actual bottleneck").
# Four channels, one property (shape without content), one fix:
#   carry     0/1650        -> logger-side, out of scope (not model text)
#   emission  3/3 shape, 0/3 resolvable -> COVERED by playbook_only rev2 P7
#                                (parse_prose_rule + propose_prose_rule already wired)
#   procedure restarts step 1 -> COVERED by apply_goal_inject (monotonic record + refusal)
#   SG        143/143 injected, 78/3640 emitted (2.1%) -> COVERED HERE (this applier)
# This applier feeds the SG ladder from subgoal-ish prose (no SG: prefix required).
# Env-gated ARC3_PROSE_PARSE_ON, default OFF. Never raises. Idempotent.
# Anchor: "user_prompt += self._retained_function_context()" (1x on 343899 B real
# bytes; disjoint insert vs goal_inject — both stack below the line, order-free).
# Usage: python3 apply_prose_parse.py /path/to/ARC3-Inference
import py_compile
import sys
from pathlib import Path


def fail(msg):
    print("PROSE_PARSE APPLIER FAIL: " + msg)
    raise SystemExit(1)


INJECT_ANCHOR = "user_prompt += self._retained_function_context()"
INJECT_NEW = ("user_prompt += self._retained_function_context()\n"
              "        try:\n"
              "            _pp_lvl = getattr(self, \"_goal_guard_level\", None)\n"
              "            _pp_n = _pp_feed_sg(self, _pp_lvl, user_prompt)\n"
              "        except Exception:\n"
              "            pass")

MECH_NEEDLE = 'getattr(self, "_h1_switches_this_level", 0)'
MECH_OLD = 'getattr(self, "_h1_switches_this_level", 0))'
MECH_NEW = ('getattr(self, "_h1_switches_this_level", 0))'
            ' + " pp_fed=%s pp_ref=%s" % (getattr(self, "_pp_fed_this_level", 0), getattr(self, "_pp_refused_this_level", 0)))')

PP_GUARD_ANCHOR = "self._noop_guard_pre_hash = state_hash"
PP_GUARD_NEW = ("self._noop_guard_pre_hash = state_hash\n"
                "        _pp_fire, _pp_detail = _pp_refuse_regressed(self, level, action_name, action_data)\n"
                "        if _pp_fire:\n"
                "            return (\"pp_refuse\", _pp_detail)")

PP_CORE = '''
import re as _reP

_PP_VERBS = ("move", "get", "open", "unlock", "go", "exit", "push",
             "collect", "carry", "use", "take", "grab", "click", "press",
             "solve", "clear", "reach", "find", "map")
_PP_ENTS = ("robot", "key", "door", "exit", "button", "box", "target",
            "switch", "lever", "gate", "tile", "room", "level", "path")
_PP_INTENT = ("need to", "needs to", "next", "then", "should",
              "plan to", "going to", "try to", "must", "will")


def _pp_parse_on() -> bool:
    try:
        import os as _osP
        return _osP.environ.get("ARC3_PROSE_PARSE_ON", "0").strip().lower() in ("1", "true", "yes", "on")
    except Exception:
        return False


def _pp_subgoals(text):
    """SG:-lines plus intent-marked prose sentences with verb+entity. Never raises."""
    out = []
    try:
        for _ln in str(text or "").splitlines():
            _s = _ln.strip()
            if len(_s) < 8 or len(_s) > 220:
                continue
            _u = _s.upper()
            if _u.startswith("SG:"):
                _t = _s[3:].strip()
                if len(_t) > 4 and _t not in out:
                    out.append(_t[:160])
                continue
            _l = _s.lower()
            if any(_k in _l for _k in _PP_INTENT):
                _v = next((_v for _v in _PP_VERBS if _v in _l), "")
                _e = next((_e for _e in _PP_ENTS if _e in _l), "")
                if _v and _e and _s not in out:
                    out.append(_s[:160])
            if len(out) >= 4:
                break
    except Exception:
        pass
    return out


_PP_STOP = ("with", "from", "that", "this", "then", "into",
            "have", "has", "are", "was", "were", "been", "the")
_PP_SYN = {"move": ("move", "go"), "get": ("get", "take", "grab", "carry", "collect"),
           "open": ("open", "unlock"), "click": ("click", "press"),
           "use": ("use", "push"), "go": ("go", "move")}


def _pp_feed_sg(agent, level, text):
    """Fill an empty SG ladder from parsed prose. Returns fed count. Never raises."""
    try:
        if not _pp_parse_on():
            return 0
        _found = _pp_subgoals(text)
        if not _found:
            return 0
        _cur = list(getattr(agent, "_hailmary_subgoals", []) or [])
        if len(_cur) >= 2:
            return 0
        _have = set()
        for _g in _cur:
            try:
                _have.add((_g.get("text", "") or "")[:60])
            except Exception:
                pass
        _added = 0
        for _t in _found:
            if _t[:60] in _have:
                continue
            _cur.append({"text": _t, "stalls": 0, "budget": 0.0})
            _have.add(_t[:60])
            _added += 1
        if _added:
            try:
                agent._hailmary_subgoals = _cur
                agent._pp_fed_this_level = int(getattr(agent, "_pp_fed_this_level", 0) or 0) + _added
            except Exception:
                pass
        return _added
    except Exception:
        return 0


def _pp_refuse_regressed(agent, level, action_name, action_data):
    """Refuse proposals matching a PASSED subgoal (idx < current). Never raises."""
    try:
        if not _pp_parse_on():
            return (False, "")
        _sgs = list(getattr(agent, "_hailmary_subgoals", []) or [])
        if len(_sgs) < 2:
            return (False, "")
        _cur = int(getattr(agent, "_hailmary_sg_idx", 0) or 0)
        if _cur <= 0 or _cur >= len(_sgs):
            return (False, "")
        _prop = (str(action_name or "") + " " + str(action_data or "")).lower()
        for _j in range(_cur):
            _txt = ""
            try:
                _txt = ((_sgs[_j].get("text", "")) or "").lower()
            except Exception:
                pass
            if not _txt:
                continue
            _verb = next((_v for _v in _PP_VERBS if _v in _txt), "")
            _syns = _PP_SYN.get(_verb, (_verb,)) if _verb else ()
            _keys = [_w for _w in _reP.split(r"\\W+", _txt)
                     if len(_w) >= 4 and _w not in _PP_STOP]
            _hit = ((any(_s in _prop for _s in _syns) and any(_k in _prop for _k in _keys))
                    or sum(1 for _k in _keys if _k in _prop) >= 2)
            if _hit:
                try:
                    agent._pp_refused_this_level = int(getattr(agent, "_pp_refused_this_level", 0) or 0) + 1
                except Exception:
                    pass
                return (True, "pp_refuse: repeats passed subgoal %d; act on current subgoal %d instead."
                        % (_j + 1, _cur + 1))
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


def main():
    if len(sys.argv) != 2:
        fail("usage: python3 apply_prose_parse.py /path/to/ARC3-Inference")
    root = Path(sys.argv[1])
    tool = root / "inference" / "agent" / "tool_agent.py"
    tt = tool.read_text(encoding="utf-8")
    if "_pp_feed_sg" not in tt:
        tt, r1 = replace_or_throw(tt, INJECT_ANCHOR, INJECT_NEW, "pp-inject")
        print("  " + r1)
        tt, r2 = replace_or_throw(tt, PP_GUARD_ANCHOR, PP_GUARD_NEW, "pp-guard")
        print("  " + r2)
        if not tt.endswith("\n"):
            tt += "\n"
        tt = tt + PP_CORE + "\n"
        tool.write_text(tt, encoding="utf-8")
    else:
        print("tool pp hook: already applied (skip)")
    # LIVE on day one: parses prompt-visible history (retained context + summaries
    # carry prior model statements — the same history class the goal applier's
    # injection proved out on at 3B). Analyzer-side text wiring is a follow-up
    # upgrade, not a blocker.
    tt2 = tool.read_text(encoding="utf-8")
    if MECH_NEEDLE in tt2 and "pp_fed=" not in tt2 and tt2.count(MECH_OLD) == 1:
        tt2 = tt2.replace(MECH_OLD, MECH_NEW, 1)
        tool.write_text(tt2, encoding="utf-8")
        print("level-mech pp counter: applied")
    else:
        print("level-mech pp counter: skipped (absent or already present)")
    try:
        py_compile.compile(str(tool), doraise=True)
    except Exception as exc:
        fail("tool_agent.py does not compile (%r)" % (exc,))
    print("PROSE_PARSE APPLIER OK")


main()
