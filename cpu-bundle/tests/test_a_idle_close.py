"""Test A — reproduce the 15-minute idle scorecard close on CPU (v6).

Uses the REAL arc-agi 0.9.9 server code (competition_mode=True) with
STALE_MINUTES=1 (minimum allowed) so the 15-minute clock becomes ~60s.

Local note: CompetitionArcadeServer does not start the gateway's
per-minute sweeper thread, so this test replicates the sweeper tick
in-process with the EXACT production functions
(get_stale_cards + should_auto_close_scorecard + close_scorecard).
HTTP GET is useless as a probe here: competition-mode cards always
answer 403 while open and 404 once deleted.

Run 1 (fresh server): open card, one RESET.
  Expect: card present, not stale, should_auto_close False.
  Idle 135s.
  Expect: card in get_stale_cards, should_auto_close True; after the
  replicated tick the card is DELETED from the manager; a further blind
  RESET raises no exception (NOT_PLAYED silence = Succeeded + 0.00).
Run 2 (fresh server): open card, RESET every 30s x5 (span ~150s).
  Expect: card NOT stale, should_auto_close False, last_update age <60s
  (periodic RESET refreshes last_update and defeats the clock — the
  core assumption behind the keep-alive fix).

Needs (Kaggle CPU notebook, internet ON):
  pip install arc-agi arcengine flask pydantic requests
Env:
  ENV_FILES = path to the competition `environment_files` dir
  (attach the competition dataset that contains it).

Usage:
  python test_a_idle_close.py
"""

import os
import sys
import time
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


def mgr_of(server):
    return server._api.arcade.scorecard_manager


def sweeper_tick(mgr):
    """Replicate the gateway's per-minute sweeper tick exactly."""
    closed = []
    for cid in mgr.get_stale_cards():
        if mgr.should_auto_close_scorecard(cid):
            scorecard, guids, _ = mgr.close_scorecard(cid, None)
            if scorecard is not None:
                closed.append(cid)
    return closed


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
    ids = discover_ids(2)
    # ---- Run 1 on server 1: idle past the stale clock ----
    s1 = competition_arcade.CompetitionArcadeServer(
        game_ids=ids,
        environments_dir=ENV_FILES,
    ).start()
    try:
        available = s1.exposed_game_ids
        print(f"server up, {len(available)} exposed envs", flush=True)
        spec = ArcadeSpec(
            operation_mode=arc_agi.OperationMode.COMPETITION,
            arc_base_url=s1.base_url,
            environments_dir="",
        )
        session = RunSession()
        g1 = GameAPI(env_name=available[0], arcade_spec=spec)
        g1.start_game(session)
        card1 = g1._scorecard_id
        m1 = mgr_of(s1)
        print(f"run1: card {card1}", flush=True)
        print(
            f"run1: fresh: present={card1 in m1.scorecards} "
            f"stale={card1 in m1.get_stale_cards()} "
            f"should_close={m1.should_auto_close_scorecard(card1)} "
            f"(expect True/False/False)",
            flush=True,
        )
        g1.execute_action(ActionInput(id=GameAction.RESET, data={}))
        print("run1: RESET issued, idling 135s ...", flush=True)
        time.sleep(135)
        stale1 = card1 in m1.get_stale_cards()
        should1 = m1.should_auto_close_scorecard(card1)
        print(
            f"run1: after idle: stale={stale1} should_close={should1} (expect True/True)",
            flush=True,
        )
        closed = sweeper_tick(m1)
        print(
            f"run1: sweeper tick closed {len(closed)}; "
            f"card present={card1 in m1.scorecards} (expect False)",
            flush=True,
        )
        # blind play after close: must not raise (NOT_PLAYED silence)
        try:
            g1.execute_action(ActionInput(id=GameAction.RESET, data={}))
            print("run1: post-close RESET executed without exception", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"run1: post-close RESET raised {exc!r}", flush=True)
    finally:
        s1.stop()
    # ---- Run 2 on a FRESH server: keep-alive RESETs every 30s ----
    s2 = competition_arcade.CompetitionArcadeServer(
        game_ids=ids,
        environments_dir=ENV_FILES,
    ).start()
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
        m2 = mgr_of(s2)
        print(f"run2: card {card2}", flush=True)
        for i in range(5):
            g2.execute_action(ActionInput(id=GameAction.RESET, data={}))
            print(f"run2: keep-alive RESET {i + 1}/5", flush=True)
            time.sleep(30)
        idle = m2.idle_duration_for(card2)
        idle_s = idle.total_seconds() if idle is not None else -1.0
        print(
            f"run2: after keep-alives: present={card2 in m2.scorecards} "
            f"stale={card2 in m2.get_stale_cards()} "
            f"should_close={m2.should_auto_close_scorecard(card2)} "
            f"idle_s={idle_s:.1f} (expect True/False/False/<60)",
            flush=True,
        )
    finally:
        s2.stop()


if __name__ == "__main__":
    main()
