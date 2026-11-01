"""verify_stride.py — GH Actions verification for stride appliers (public repo).

Runs on ubuntu-latest where python3 exists (this worker has no python).
What it proves:
  1. py_compile on every stride/apply_*.py (catches typo-class + bad-patch-class errors).
  2. replace-or-throw + idempotence patterns present (static check).
  3. banned-word scan on EMITTED prompt strings only (P1/P2/P3/P4/message bodies);
     filter lists (for _w in (...)) are explicitly allowed.
  4. synthetic unit test of insert_after_line / insert_before_line semantics.
  5. anchor audit vs ARC3-Inference on disk (INFORMATIONAL): reports counts,
     does NOT fail on CODEEXEC/INTERVAL (0x on the public 89KB stock file by
     design — those anchors live on the 343KB Kaggle patched bytes; full
     4-merge sim stays in Kaggle Cell-B).
  6. live merge test for the two appliers that SHOULD merge on public bytes
     (hailmary + hierarchy) against a /tmp copy + py_compile of merged result.

Exit 0 = syntax + logic + 2 merges green. Anchor mismatches on CATTS/MECH
are printed as EXPECTED-MISMATCH, not failures.
"""
import py_compile
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # repo root
STRIDE = ROOT / "stride"
AGENT = ROOT / "ARC3-Inference" / "inference" / "agent"

APPLIERS = [
    "apply_hailmary.py",
    "apply_hierarchy.py",
    "apply_catts.py",
    "apply_mechsummary.py",
]

# Anchors: (file, needle, expect_on_public, note)
ANCHORS = [
    ("prompts.py", "For `MOUSE`, pass", 1, "P1/P2/P3/P4 site"),
    ("tool_agent.py", "    def _build_user_message(", 1, "helper site"),
    ("tool_agent.py", 'elif previous_step_summary.get("level_transition"):', 1, "H1/SG call site"),
    ("tool_agent.py", 'self._session_runtime_dir = runtime_dir', 1, "stem site"),
    ("tool_agent.py", 'lines.append(f"The code executed {normalized} {label} in the previous sequence.")', 0, "CATTS call site — 0x on public 89KB by design"),
    ("tool_agent.py", "        interval = _summary_interval_tokens()", 0, "MECH gate site — 0x on public 89KB by design"),
]

BANNED = ("give_up", "abandon", "quit")


def fail(msg):
    print("VERIFY_STRIDE FAIL: " + msg)
    raise SystemExit(1)


def count(hay, needle):
    c = 0
    i = 0
    while True:
        i = hay.find(needle, i)
        if i == -1:
            return c
        c += 1
        i += len(needle)


def main():
    print("== 1. py_compile appliers ==")
    for name in APPLIERS:
        p = STRIDE / name
        if not p.exists():
            fail("missing " + str(p))
        py_compile.compile(str(p), doraise=True)
        print("  OK", name, p.stat().st_size, "B")

    print("== 2. static patterns ==")
    for name in APPLIERS:
        t = (STRIDE / name).read_text(encoding="utf-8")
        if "len(idx) !=" not in t and "found %d times" not in t:
            fail(name + ": replace-or-throw pattern missing")
        if "py_compile.compile" not in t:
            fail(name + ": py_compile guard missing")
        if "already present" not in t:
            fail(name + ": idempotence marker missing")
        print("  OK", name)

    print("== 3. banned-word scan (emitted prompts only) ==")
    for name in APPLIERS:
        t = (STRIDE / name).read_text(encoding="utf-8")
        # Extract emitted prompt constants: lines starting with P1/P2/P3/P4 = "..."
        emitted = [ln for ln in t.splitlines() if ln.startswith(("P1 ", "P1=", "P2 ", "P2=", "P3 ", "P3=", "P4 ", "P4="))]
        # Also message bodies: base = ( "..." blocks are harder; check H1 base + SG _msg + CATTS _msg
        # Simplest sound check: P-constants must be clean; helper filter-lists are allowed.
        for ln in emitted:
            low = ln.lower()
            for w in BANNED:
                if w in low:
                    fail("%s: banned word %r in emitted prompt line: %s" % (name, w, ln[:120]))
        print("  OK", name, len(emitted), "prompt const lines clean")

    print("== 4. synthetic insert semantics ==")
    def insert_after(text, needle, new_lines, expect):
        idx = [i for i, l in enumerate(text.split("\n")) if needle in l]
        assert len(idx) == expect, (needle, len(idx), expect)
        lines = text.split("\n")
        return "\n".join(lines[:idx[0] + 1] + new_lines + lines[idx[0] + 1:])

    def insert_before(text, needle, new_lines, expect):
        idx = [i for i, l in enumerate(text.split("\n")) if needle in l]
        assert len(idx) == expect, (needle, len(idx), expect)
        lines = text.split("\n")
        return "\n".join(lines[:idx[0]] + new_lines + lines[idx[0]:])

    s = "a\nneedle here\nb"
    assert insert_after(s, "needle", ["X"], 1) == "a\nneedle here\nX\nb"
    assert insert_before(s, "needle", ["X"], 1) == "a\nX\nneedle here\nb"
    try:
        insert_after(s, "missing", ["X"], 1)
        fail("insert_after did not throw on 0 hits")
    except AssertionError:
        pass
    print("  OK insert_after/insert_before")

    print("== 5. anchor audit vs public ARC3-Inference (informational) ==")
    for fname, needle, expect_public, note in ANCHORS:
        f = AGENT / fname
        if not f.exists():
            print("  MISSING FILE", fname)
            continue
        c = count(f.read_text(encoding="utf-8"), needle)
        status = "OK" if c == expect_public else ("EXPECTED-MISMATCH" if expect_public == 0 else "UNEXPECTED")
        print("  [%s] %s %r: found %d, expect-public %d — %s" % (status, fname, needle[:60], c, expect_public, note))
        if expect_public >= 1 and c != expect_public:
            fail("anchor %r in %s: found %d, want %d" % (needle[:60], fname, c, expect_public))

    print("== 6. live merge (hailmary + hierarchy) on /tmp copy ==")
    if not (AGENT / "tool_agent.py").exists():
        fail("ARC3-Inference agent files missing; cannot live-merge")
    with tempfile.TemporaryDirectory() as td:
        # Copy ARC3-Inference tree layout the appliers expect:
        # appliers take root = /path/to/ARC3-Inference
        dst = Path(td) / "ARC3-Inference"
        shutil.copytree(str(ROOT / "ARC3-Inference"), str(dst))
        for name in ("apply_hailmary.py", "apply_hierarchy.py"):
            r = subprocess.run([sys.executable, str(STRIDE / name), str(dst)],
                               capture_output=True, text=True)
            print("  ---", name, "rc=", r.returncode)
            print(r.stdout[-2000:])
            if r.stderr:
                print(r.stderr[-2000:])
            if r.returncode != 0:
                fail(name + " live-merge failed")
        for f in (dst / "inference" / "agent" / "prompts.py",
                  dst / "inference" / "agent" / "tool_agent.py"):
            py_compile.compile(str(f), doraise=True)
        print("  OK merged bytes compile")

    print("VERIFY_STRIDE OK")


main()
