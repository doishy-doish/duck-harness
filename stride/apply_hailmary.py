# apply_hailmary.py — Hail Mary prompt+H1 merge (P1/P2 prompt, H1 ratio line, stem store).
# Base: v25 banked bits. Line-oriented replace-or-throw: short escape-free needles,
# insert after the matched LINE, assert exactly 1 hit or abort. py_compile-guarded. Idempotent.
# Hunks: (1) prompts.py P1+P2 after MOUSE line; (2) tool_agent.py H1 helper before
# _build_user_message; (3) stem store in _ensure_session; (4) H1 call in level-transition branch.
# Guards/persist/scope/H1-on/baselines-path are ENV ONLY (cells doc). Death guard HELD.
# Usage: python3 apply_hailmary.py /path/to/ARC3-Inference
import py_compile
import sys
from pathlib import Path

P1 = "    \"- How you are scored (RHAE): only completed levels count; an incomplete level is worth zero. Levels are weighted by index, so a deep level is worth more than a shallow one. Efficiency per level is capped: above the cap, extra actions cost nothing. Play to complete or cut: push a level you are close to finishing, cut a level that is not converting, do not half-explore.\\n\""
P2 = "    \"- Track sub-goal progress, not motion: a level nearly done with few actions spent deserves more attempts; a level at no sub-goals after many actions does not. The action-result flags (game_over, level_completed, done) plus score increases are your progress feed; use them to tell progress from motion.\\n\""
MOUSE_NEEDLE = "For `MOUSE`, pass"
ELIF_NEEDLE = 'elif previous_step_summary.get("level_transition"):'
HELPER_DEF_ANCHOR = "    def _build_user_message("
STEM_ANCHOR = "self._session_runtime_dir = runtime_dir"

H1_HELPER = '''_HAILMARY_BASELINES_CACHE = None


def _hailmary_par_line(agent, level, used_actions):
    """H1 human-ratio line. Harness-filled numbers; fail-closed to ''."""
    global _HAILMARY_BASELINES_CACHE
    try:
        import json as _json
        import os as _os
        if _os.environ.get("ARC3_HAILMARY_H1", "").strip().lower() not in ("1", "true", "yes", "on"):
            return ""
        path = _os.environ.get("ARC3_HAILMARY_BASELINES", "").strip()
        if not path:
            return ""
        if _HAILMARY_BASELINES_CACHE is None:
            with open(path, "r", encoding="utf-8") as _fh:
                _HAILMARY_BASELINES_CACHE = _json.load(_fh)
        table = _HAILMARY_BASELINES_CACHE
        stem = str(getattr(agent, "_hailmary_run_stem", "") or "")
        game_key = ""
        if isinstance(table, dict):
            for _k in sorted(table.keys(), key=len, reverse=True):
                if _k and _k in stem:
                    game_key = _k
                    break
        pars = table.get(game_key, []) if isinstance(table, dict) else []
        if not isinstance(pars, list) or not (1 <= int(level) <= len(pars)):
            return ""
        par = float(pars[int(level) - 1])
        if par <= 0:
            return ""
        ratio = float(used_actions) / par
        base = (
            "Human par for this level: %d actions (benchmark). You have used %d (%.0f%% of par) with budget left. "
            "With no progress, SWITCH APPROACH. Name a different approach and take one action from it."
            % (int(par), int(used_actions), ratio * 100.0)
        )
        try:
            share = float(_os.environ.get("ARC3_PER_GAME_SHARE_S", "0") or 0)
        except Exception:
            share = 0.0
        tier = ""
        try:
            if par > 0 and float(used_actions) > 4.0 * float(par):
                tier = " You are past 4x par on this level. Prefer levels near completion with few actions spent; keep new search cheap."
            elif par > 0 and float(used_actions) > 2.0 * float(par):
                tier = " You are past 2x par on this level. Change action class on the next action."
            if share > 0 and float(used_actions) > share:
                tier += " Run budget is tight: remaining time divided by remaining games is below your spend here."
        except Exception:
            pass
        msg = base + tier
        low = msg.lower()
        for _w in ("give_up", "abandon", "quit"):
            if _w in low:
                return ""
        if " stop " in (" " + low + " "):
            return ""
        return msg
    except Exception:
        return ""
'''

H1_CALL = '''                try:
                    _h1_used = max(0, int(action_num) - int(self._actions_at_level_start))
                except Exception:
                    _h1_used = 0
                _h1_level = 1
                try:
                    _h1_level = int(current_frame.level) if current_frame is not None else 1
                except Exception:
                    _h1_level = 1
                try:
                    _h1_line = _hailmary_par_line(self, _h1_level, _h1_used)
                except Exception:
                    _h1_line = ""
                if _h1_line:
                    lines.append(_h1_line)'''


def fail(msg):
    print("HAILMARY APPLIER FAIL: " + msg)
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
        fail("usage: python3 apply_hailmary.py /path/to/ARC3-Inference")
    root = Path(sys.argv[1])
    prompts = root / "inference" / "agent" / "prompts.py"
    tool = root / "inference" / "agent" / "tool_agent.py"
    pt = prompts.read_text(encoding="utf-8")
    tt = tool.read_text(encoding="utf-8")
    if "How you are scored (RHAE)" not in pt:
        pt = insert_after_line(pt, MOUSE_NEEDLE, [P1, P2], 1, "prompts-p1p2")
        prompts.write_text(pt, encoding="utf-8")
    else:
        print("P1/P2 already present; skipping prompts hunk")
    if "_hailmary_par_line" not in tt:
        assert_anchor_once(tt, HELPER_DEF_ANCHOR, 1, "tool-helper")
        tt = insert_after_line(tt, STEM_ANCHOR, ['            self._hailmary_run_stem = getattr(state_path, "stem", "")'], 1, "tool-stem")
        tt = insert_after_line(tt, ELIF_NEEDLE, H1_CALL.split("\n"), 1, "tool-h1call")
        if not tt.endswith("\n"):
            tt += "\n"
        tt = tt + H1_HELPER + "\n"
        tool.write_text(tt, encoding="utf-8")
    else:
        print("H1 already present; skipping tool hunks")
    for f in (prompts, tool):
        py_compile.compile(str(f), doraise=True)
    print("HAILMARY APPLIER OK")


main()
