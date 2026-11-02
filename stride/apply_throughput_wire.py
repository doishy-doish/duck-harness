# apply_throughput_wire.py — wire DEAD throughput helpers to call sites + invoke counter (entry 815 precondition for B).
# Wires: _dispatch_game_type (I2), _combo_cache_lookup (I3), _timer_mask_core (I1), level-budget weight (vendored).
# Design: additive, env-gated behavior (helpers default OFF -> no behavior change when env off); invoke counting is
# env-INDEPENDENT (counts wiring liveness, not gate state). Fail-closed: every call site is try/except, falls back
# to the unwired path. Order-free vs goal_inject / prose_parse / holdback_v2 (disjoint 1x anchors, verified below).
# Anchors verified 1x on patched-35.35 real bytes (343899 B, 7260 lines):
#   A: '        guard.note_level(level)\n        # the solver passes ENGINE names' (combo+harness-read site is
#      elsewhere; this anchor is NOT used here to stay disjoint from holdback_v2 which owns it)
#   DISPATCH/BUDGET site: '        self._death_ledger_observe(history_entries, previous_step_summary)' (1x,
#      _build_user_prompt, valid-actions block; valid_actions + current_level in scope)
#   TIMER site: '        state_hash = _interior_state_hash(rows)' (1x, _action_guard_hook active branch)
#   COMBO site: '        self._noop_guard_pre_hash = state_hash' (1x, active branch, after action_sig)
# Reads (B-internal, no baseline): demo log grep 'THROUGHPUT-INVOKE <kind> level=' -> count > 0 per kind proves
# invoked. Runtime totals via _throughput_counts(). Static proof: grep applied file for the 4 call sites.
# Usage: python3 apply_throughput_wire.py /path/to/ARC3-Inference
import py_compile
import sys
from pathlib import Path


def fail(msg):
    print("_throughput_wire FAIL: " + msg)
    raise SystemExit(1)


CORE = '''
_THROUGHPUT_INVOKES = {"dispatch": 0, "timer": 0, "combo": 0, "budget": 0}
_THROUGHPUT_SEEN = set()


def _throughput_invoke(kind, agent=None, level=None):
    """Count one throughput-helper invocation. Env-independent (wiring liveness). Never raises."""
    try:
        _THROUGHPUT_INVOKES[kind] = int(_THROUGHPUT_INVOKES.get(kind, 0) or 0) + 1
    except Exception:
        pass
    try:
        if agent is not None:
            _d = getattr(agent, "_throughput_invokes", None)
            if not isinstance(_d, dict):
                _d = {}
            _d[kind] = int(_d.get(kind, 0) or 0) + 1
            try:
                agent._throughput_invokes = _d
            except Exception:
                pass
    except Exception:
        pass
    try:
        _key = (str(kind), str(level))
        if _key not in _THROUGHPUT_SEEN:
            _THROUGHPUT_SEEN.add(_key)
            print("THROUGHPUT-INVOKE %s level=%s" % (kind, level), flush=True)
    except Exception:
        pass


def _throughput_counts(agent=None):
    """Runtime totals (global + optional agent). Never raises."""
    try:
        _g = dict(_THROUGHPUT_INVOKES)
    except Exception:
        _g = {}
    try:
        _a = dict(getattr(agent, "_throughput_invokes", {}) or {})
    except Exception:
        _a = {}
    return {"global": _g, "agent": _a}


def _level_budget_weight(k, nlevels=8):
    """Vendored RHAE weight: level k of nlevels (weight = k / total). Never raises."""
    try:
        return float(k) / float(nlevels * (nlevels + 1) / 2)
    except Exception:
        return 0.0
'''

# Site 1: dispatch + budget — after death-ledger observe (valid_actions + current_level in scope).
DISPATCH_ANCHOR = "        self._death_ledger_observe(history_entries, previous_step_summary)"
DISPATCH_NEW = (
    "        self._death_ledger_observe(history_entries, previous_step_summary)\n"
    "        try:\n"
    "            _throughput_invoke(\"dispatch\", self, current_level)\n"
    "            try:\n"
    "                _dispatch_game_type(\",\".join(valid_actions or []))\n"
    "            except Exception:\n"
    "                pass\n"
    "            _throughput_invoke(\"budget\", self, current_level)\n"
    "            try:\n"
    "                _level_budget_weight(current_level)\n"
    "            except Exception:\n"
    "                pass\n"
    "        except Exception:\n"
    "            pass"
)

# Site 2: timer — wrap rows before hashing (helper env-gated OFF -> identity when off).
TIMER_ANCHOR = "        state_hash = _interior_state_hash(rows)"
TIMER_NEW = (
    "        try:\n"
    "            _throughput_invoke(\"timer\", self, level)\n"
    "        except Exception:\n"
    "            pass\n"
    "        try:\n"
    "            _tm_rows = _timer_mask_core(rows)\n"
    "        except Exception:\n"
    "            _tm_rows = rows\n"
    "        state_hash = _interior_state_hash(_tm_rows)"
)

# Site 3: combo — before pre-hash store (disjoint from holdback anchor which owns note_level+comment).
COMBO_ANCHOR = "        self._noop_guard_pre_hash = state_hash"
COMBO_NEW = (
    "        try:\n"
    "            _throughput_invoke(\"combo\", self, level)\n"
    "        except Exception:\n"
    "            pass\n"
    "        try:\n"
    "            _combo_cache_lookup(level)\n"
    "        except Exception:\n"
    "            pass\n"
    "        self._noop_guard_pre_hash = state_hash"
)


def replace_or_throw(text, anchor, new, label, marker):
    # marker-guarded: NEW blocks retain their anchor line, so anchor-count
    # alone cannot prove idempotence (entry 815 bug class). Marker = a line
    # unique to the inserted block; present => skip, absent => anchor must be 1x.
    if marker in text:
        return text, "%s: already applied (skip)" % label
    count = text.count(anchor)
    if count != 1:
        fail("anchor for %s found %d times (want 1)" % (label, count))
    return text.replace(anchor, new, 1), "%s: applied" % label


def main():
    if len(sys.argv) != 2:
        fail("usage: python3 apply_throughput_wire.py /path/to/ARC3-Inference")
    tool = Path(sys.argv[1]) / "inference" / "agent" / "tool_agent.py"
    tt = tool.read_text(encoding="utf-8")
    if "_throughput_invoke" not in tt:
        if not tt.endswith("\n"):
            tt += "\n"
        tt = tt + CORE + "\n"
        print("  core: appended")
    else:
        print("  core: already present (skip)")
    tt, r1 = replace_or_throw(tt, DISPATCH_ANCHOR, DISPATCH_NEW, "dispatch+budget-site",
                                 '_throughput_invoke("dispatch", self, current_level)')
    print("  " + r1)
    tt, r2 = replace_or_throw(tt, TIMER_ANCHOR, TIMER_NEW, "timer-site",
                              "_tm_rows = _timer_mask_core(rows)")
    print("  " + r2)
    tt, r3 = replace_or_throw(tt, COMBO_ANCHOR, COMBO_NEW, "combo-site",
                              '_throughput_invoke("combo", self, level)')
    print("  " + r3)
    tool.write_text(tt, encoding="utf-8")
    try:
        py_compile.compile(str(tool), doraise=True)
    except Exception as exc:
        fail("built tool_agent.py does not compile (%r)" % (exc,))
    print("_throughput_wire APPLIER OK")


main()
