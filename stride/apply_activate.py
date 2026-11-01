# apply_activate.py — v28 per-turn activation for SG/CATTS/abstention.
# Finding (LAB-LOG 745, firsthand on v27 demo ar25 requests, 46MB):
# v27 inserted H1/SG/CATTS/abstention calls after the level_transition ELIF branch.
# That branch runs on transition turns only, and the CATTS/abstention helpers
# return "" on transition turns by design. Net: ar25 showed 292 H1 refs (level-start
# par lines, working as designed) but 0 SG / 0 CATTS / 0 abstention emissions —
# including a 12-identical-action run that met the abstention trigger. SG is doubly
# dead: _hailmary_sg_parse is never called (no site feeds it model text) and
# _hailmary_sg_line is never called (SG_CALL only advances stalls/rotates).
# Fix (behavior, fail-closed preserved): ONE per-turn block inserted BEFORE the
# per-turn game_over anchor (same _build_user_prompt suite: lines/self/
# previous_step_summary/history_entries all in scope). It (1) parses SG lines from
# recent assistant messages in self._history_messages, (2) advances/rotates
# subgoals, (3) injects the SG line, (4) runs the CATTS arbiter append,
# (5) runs the abstention rotation append. H1 and MECH hunks untouched.
# Runs AFTER hailmary+hierarchy+catts+abstention in the cell chain (asserts their
# call blocks present 1x each). Dead ELIF blocks left in place (provable no-ops).
# Fire-only prints ride the logs-stream for the demo read.
# Usage: python3 apply_activate.py /path/to/ARC3-Inference
import py_compile
import sys
from pathlib import Path

GAMEOVER_NEEDLE = 'if previous_step_summary.get("game_over"):'
SG_NEEDLE = "self._hailmary_sg_idx = (_i + 1) % len(_sgs)"
CATTS_NEEDLE = "_catts_line = _hailmary_catts_line(history_entries, previous_step_summary)"
ABSTAIN_NEEDLE = "_abstain_line = _hailmary_abstain_line(history_entries, previous_step_summary)"
MARKER = "ARC3_ACTIVATE_V28"

ACTIVATE_BLOCK = '''            # ARC3_ACTIVATE_V28: per-turn activation (v27 left SG/CATTS/abstain
            # transition-gated and self-suppressed: 0 emissions in v27 demo ar25).
            try:
                _act_parts = []
                try:
                    _act_hist = list(getattr(self, '_history_messages', []) or [])[-6:]
                    for _act_m in _act_hist:
                        if isinstance(_act_m, dict) and _act_m.get('role') == 'assistant':
                            _act_c = _act_m.get('content')
                            if isinstance(_act_c, str):
                                _act_parts.append(_act_c)
                            elif isinstance(_act_c, list):
                                for _act_p in _act_c:
                                    if isinstance(_act_p, dict) and isinstance(_act_p.get('text'), str):
                                        _act_parts.append(_act_p['text'])
                                    else:
                                        _act_parts.append(str(_act_p))
                            elif _act_c is not None:
                                _act_parts.append(str(_act_c))
                except Exception:
                    pass
                if _act_parts:
                    try:
                        _hailmary_sg_parse(self, '\\n'.join(_act_parts))
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                _sgs = list(getattr(self, '_hailmary_subgoals', []) or [])
                if _sgs:
                    _i = int(getattr(self, '_hailmary_sg_idx', 0) or 0) % len(_sgs)
                    _g = _sgs[_i]
                    _g['stalls'] = int(_g.get('stalls', 0) or 0) + 1
                    _b = float(_g.get('budget', 0) or 0)
                    if _b > 0 and _g['stalls'] > _b:
                        try:
                            _note = "SG '%s' stalled after %d actions" % (_g.get('text', '')[:80], _g['stalls'])
                            _pb = getattr(self, '_hailmary_playbook_mem', None)
                            if isinstance(_pb, list):
                                _pb.append(_note)
                        except Exception:
                            pass
                        self._hailmary_sg_idx = (_i + 1) % len(_sgs)
                        self._hailmary_subgoals[_i]['stalls'] = 0
                        if self._hailmary_sg_idx == 0:
                            self._hailmary_subgoals = []
            except Exception:
                pass
            try:
                _sg_line2 = _hailmary_sg_line(self)
            except Exception:
                _sg_line2 = ''
            if _sg_line2:
                lines.append(_sg_line2)
                try:
                    print('ARC3_ACTIVATE sg: ' + str(_sg_line2)[:120])
                except Exception:
                    pass
            try:
                _catts_line2 = _hailmary_catts_line(history_entries, previous_step_summary)
            except Exception:
                _catts_line2 = ''
            if _catts_line2:
                lines.append(_catts_line2)
                try:
                    print('ARC3_ACTIVATE catts: ' + str(_catts_line2)[:120])
                except Exception:
                    pass
            try:
                _abstain_line2 = _hailmary_abstain_line(history_entries, previous_step_summary)
            except Exception:
                _abstain_line2 = ''
            if _abstain_line2:
                lines.append(_abstain_line2)
                try:
                    print('ARC3_ACTIVATE abstain: ' + str(_abstain_line2)[:120])
                except Exception:
                    pass'''


def fail(msg):
    print("ACTIVATE APPLIER FAIL: " + msg)
    raise SystemExit(1)


def main():
    if len(sys.argv) != 2:
        fail("usage: python3 apply_activate.py /path/to/ARC3-Inference")
    root = Path(sys.argv[1])
    tool = root / "inference" / "agent" / "tool_agent.py"
    tt = tool.read_text(encoding="utf-8")
    if MARKER in tt:
        print("ARC3_ACTIVATE_V28 already present; skipping")
        return
    for needle, tag in ((SG_NEEDLE, "sg-call"), (CATTS_NEEDLE, "catts-call"),
                        (ABSTAIN_NEEDLE, "abstain-call"), (GAMEOVER_NEEDLE, "gameover-anchor")):
        idx = [i for i, l in enumerate(tt.split("\n")) if needle in l]
        if len(idx) != 1:
            fail("%s: needle %r found %d times, want 1" % (tag, needle[:60], len(idx)))
    lines = tt.split("\n")
    pos = next(i for i, l in enumerate(lines) if GAMEOVER_NEEDLE in l)
    tt = "\n".join(lines[:pos] + ACTIVATE_BLOCK.split("\n") + lines[pos:])
    tool.write_text(tt, encoding="utf-8")
    py_compile.compile(str(tool), doraise=True)
    print("ACTIVATE APPLIER OK")


main()
