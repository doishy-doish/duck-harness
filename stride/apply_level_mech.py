# apply_level_mech.py — unified per-level trace (add-on, ~10 lines runtime).
# Base: playbook applier already applied (P7 prints PLAYBOOK_LEVEL per level-up).
# This adds LEVEL_MECH alongside it: game + level + playbook deltas + optional
# gate/audit/H1 counters (zeros until those appliers fill them). Instrumentation
# only, never raises, idempotent. Rebuild .ipynb blob after (sha changes).
import py_compile
import sys
from pathlib import Path

MECH_FUNC = '''
def level_mech_line(game_label, level, extra=""):
    # Unified per-level trace. Extra carries "gate_fires=N audit=N h1=N tier=X".
    try:
        st = playbook_stats()
        base = "LEVEL_MECH game=%s level=%s rules=%d pending=%d" % (
            str(game_label), str(level), st["rules"], st["pending"])
        return base + ((" " + str(extra)) if extra else "")
    except Exception:
        return ""
'''

MECH_ANCHOR = "def boundary_readout_line(game_label):"
LEVEL_PRINT_ANCHOR = 'print("PLAYBOOK_LEVEL admitted=%d rejected=%d rules=%d (%+d)" % (_pb_admitted, _pb_rejected, _pb_after, _pb_after - _pb_before))'
LEVEL_PRINT_NEW = ('print("PLAYBOOK_LEVEL admitted=%d rejected=%d rules=%d (%+d)" % (_pb_admitted, _pb_rejected, _pb_after, _pb_after - _pb_before))\n'
                   '                _lm_extra = "pb_admitted=%d pb_rejected=%d gate_fires=%s audit=%s h1=%s" % (_pb_admitted, _pb_rejected, getattr(self, "_gate_fires_this_level", 0), getattr(self, "_audit_fires_this_level", 0), getattr(self, "_h1_switches_this_level", 0))\n'
                   '                print(_playbook_memory.level_mech_line(getattr(getattr(self, "_session_runtime_dir", None), "name", "unknown"), summary.get("level", -1), _lm_extra))')


def replace_or_throw(text, anchor, new, label):
    count = text.count(anchor)
    if new in text and count == 0:
        return text, "%s: already applied (skip)" % label
    if count != 1:
        raise SystemExit("apply_level_mech FAIL: anchor for %s found %dx (want 1)" % (label, count))
    return text.replace(anchor, new), "%s: applied" % label


def main():
    base = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    pb_path = base / "inference" / "agent" / "playbook_memory.py"
    pb_text = pb_path.read_text(encoding="utf-8")
    pb_text, r1 = replace_or_throw(pb_text, MECH_ANCHOR, MECH_FUNC + "\n" + MECH_ANCHOR, "level_mech func")
    pb_path.write_text(pb_text, encoding="utf-8")
    try:
        py_compile.compile(str(pb_path), doraise=True)
    except Exception as exc:
        raise SystemExit("apply_level_mech FAIL: playbook_memory does not compile (%r)" % (exc,))
    tool_rel = "inference/agent/tool_agent.py"
    path = base / tool_rel
    text = path.read_text(encoding="utf-8")
    text, r2 = replace_or_throw(text, LEVEL_PRINT_ANCHOR, LEVEL_PRINT_NEW, "P7 LEVEL_MECH print")
    path.write_text(text, encoding="utf-8")
    try:
        py_compile.compile(str(path), doraise=True)
    except Exception as exc:
        raise SystemExit("apply_level_mech FAIL: tool_agent does not compile (%r)" % (exc,))
    print("LEVEL_MECH_APPLIED")
    print("  " + r1)
    print("  " + r2)
    print("  playbook_memory.py compiles: yes")
    print("  tool_agent.py compiles: yes")


if __name__ == "__main__":
    main()
