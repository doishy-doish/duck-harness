"""Test A — reproduce the 15-minute idle scorecard close on CPU.

Uses the REAL arc-agi 0.9.9 server code (competition_mode=True) with
STALE_MINUTES=1 (minimum allowed) so the 15-minute clock becomes ~60s.

Run 1 (no keep-alive): open card, one RESET, idle 75s.
  Expect: scorecard auto-closed, levels_completed == 0.
  Then one more RESET (blind play): no exception, score stays 0.
  That is the Succeeded + 0.00 signature.

Run 2 (keep-alive): open card, RESET every 30s x3 (spans 90s > 60s idle).
  Expect: scorecard still open, actions recorded.

Needs (Kaggle CPU notebook, internet ON):
  pip install arc-agi arcengine flask pydantic requests
Env:
  ENV_FILES = path to the competition `environment_files` dir
  (attach the competition dataset that contains it).

Usage:
  python test_a_idle_close.py
"""

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

BUNDLE = Path(os.environ.get("CPU_BUNDLE", "/kaggle/working/cpu_bundle"))

# MUST precede any arc_agi import: the idle timeout is read at import time.
os.environ["STALE_MINUTES"] = "1"
os.environ.setdefault("ARC_API_KEY", "test-key-123")

sys.path.insert(0, str(BUNDLE / "taaf-src"))
sys.path.insert(0, str(BUNDLE / "ARC3-Inference"))

from taaf import competition_arcade  # noqa: E402
from taaf.game import RunSession  # noqa: E402
from taaf.game_api import ArcadeSpec, GameAPI  # noqa: E402
import arc_agi  # noqa: E402
from arcengine import ActionInput, GameAction  # noqa: E402

ENV_FILES = os.environ["ENV_FILES"]
BASE = None


def rest(method, path, payload=None, timeout=15):
    url = BASE + path
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001 - surface HTTP errors as text
        return -1, repr(exc)


def discover_ids(n):
    """List local env game IDs without re_arc (official_game_ids needs it)."""
    import logging

    probe = arc_agi.Arcade(
        operation_mode=arc_agi.OperationMode.OFFLINE,
        environments_dir=ENV_FILES,
        logger=logging.getLogger("cpu-probe"),
    )
    ids = [env.game_id for env in probe.available_environments]
    print(f"probe: {len(ids)} envs, sample {ids[:5]}", flush=True)
    assert len(ids) >= n, f"need >={n} envs, found {len(ids)}"
    return ids[:n]


def main():
    global BASE
    ids = discover_ids(2)
    # Run 1 on server 1: idle past the stale clock.
    s1 = competition_arcade.CompetitionArcadeServer(
        game_ids=ids,
        environments_dir=ENV_FILES,
    ).start()
    BASE = s1.base_url
    try:
        available = s1.exposed_game_ids
        print(f"server up at {BASE}, {len(available)} exposed envs", flush=True)
        gid = available[0]

        spec = ArcadeSpec(
            operation_mode=arc_agi.OperationMode.COMPETITION,
            arc_base_url=s1.base_url,
            environments_dir="",
        )
        session = RunSession()

        # ---- Run 1: idle past the stale clock ----
        g1 = GameAPI(env_name=gid, arcade_spec=spec)
        g1.start_game(session)
        card1 = g1._scorecard_id
        print(f"run1: card {card1}", flush=True)
        g1.execute_action(ActionInput(id=GameAction.RESET, data={}))
        print("run1: RESET issued, idling 75s ...", flush=True)
        time.sleep(75)
        status, body = rest("GET", f"/api/scorecard/{card1}")
        print(f"run1: GET after idle -> status={status} body={body[:300]}", flush=True)

        # blind play after close: must not raise, must not score
        try:
            g1.execute_action(ActionInput(id=GameAction.RESET, data={}))
            print("run1: post-close RESET executed without exception", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"run1: post-close RESET raised {exc!r}", flush=True)
        status2, body2 = rest("GET", f"/api/scorecard/{card1}")
        print(f"run1: GET after blind RESET -> status={status2} body={body2[:300]}", flush=True)

        # ---- Run 2 on a FRESH server: keep-alive RESETs every 30s ----
        # (fresh arcade: run1's closed card must not leak into run2)
    finally:
        s1.stop()
    s2 = competition_arcade.CompetitionArcadeServer(
        game_ids=ids,
        environments_dir=ENV_FILES,
    ).start()
    BASE = s2.base_url
    try:
        available2 = s2.exposed_game_ids
        spec2 = ArcadeSpec(
            operation_mode=arc_agi.OperationMode.COMPETITION,
            arc_base_url=s2.base_url,
            environments_dir="",
        )
        session2 = RunSession()
        g2 = GameAPI(env_name=available2[1], arcade_spec=spec2)
        g2.start_game(session2)
        card2 = g2._scorecard_id
        print(f"run2: card {card2}", flush=True)
        for i in range(4):
            g2.execute_action(ActionInput(id=GameAction.RESET, data={}))
            print(f"run2: keep-alive RESET {i + 1}/4", flush=True)
            time.sleep(30)
        status3, body3 = rest("GET", f"/api/scorecard/{card2}")
        print(f"run2: GET after keep-alives -> status={status3} body={body3[:300]}", flush=True)
    finally:
        s2.stop()


if __name__ == "__main__":
    main()
