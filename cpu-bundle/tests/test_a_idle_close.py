"""Test A — reproduce the 15-minute idle scorecard close on CPU.

Uses the REAL arc-agi 0.9.9 server code (competition_mode=True) with
STALE_MINUTES=1 (minimum allowed) so the 15-minute clock becomes ~60s.
The gateway sweeper ticks every 60s and deletes stale cards, so an idle
card is gone (HTTP 404) shortly after 60s idle.

Run 1 (fresh server): open card, one RESET, GET (expect 200), idle 135s,
  GET (expect 404 = auto-closed + deleted), blind RESET (expect no
  exception = post-close silence, the Succeeded + 0.00 signature).
Run 2 (fresh server): open card, RESET every 30s x5 (span ~150s),
  GET (expect 200 = periodic RESET refreshes last_update and defeats
  the clock — the core assumption behind the keep-alive fix).

Auth note: GET /api/scorecard/<id> requires the X-API-Key header
(default "1234"); without it every GET 404s regardless of state.

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
API_KEY = os.environ.get("ARC_API_KEY", "test-key-123")
BASE = None


def rest(method, path, payload=None, timeout=15):
    url = BASE + path
    data = None
    headers = {"X-API-Key": API_KEY}
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
    # ---- Run 1 on server 1: idle past the stale clock ----
    s1 = competition_arcade.CompetitionArcadeServer(
        game_ids=ids,
        environments_dir=ENV_FILES,
    ).start()
    BASE = s1.base_url
    try:
        available = s1.exposed_game_ids
        print(f"server up at {BASE}, {len(available)} exposed envs", flush=True)
        spec = ArcadeSpec(
            operation_mode=arc_agi.OperationMode.COMPETITION,
            arc_base_url=s1.base_url,
            environments_dir="",
        )
        session = RunSession()
        g1 = GameAPI(env_name=available[0], arcade_spec=spec)
        g1.start_game(session)
        card1 = g1._scorecard_id
        print(f"run1: card {card1}", flush=True)
        s0, b0 = rest("GET", f"/api/scorecard/{card1}")
        print(f"run1: GET fresh card -> status={s0} (expect 200)", flush=True)
        g1.execute_action(ActionInput(id=GameAction.RESET, data={}))
        print("run1: RESET issued, idling 135s ...", flush=True)
        time.sleep(135)
        status, body = rest("GET", f"/api/scorecard/{card1}")
        print(f"run1: GET after idle -> status={status} body={body[:200]} (expect 404)", flush=True)

        # blind play after close: must not raise, must not score
        try:
            g1.execute_action(ActionInput(id=GameAction.RESET, data={}))
            print("run1: post-close RESET executed without exception", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"run1: post-close RESET raised {exc!r}", flush=True)
    finally:
        s1.stop()
    # ---- Run 2 on a FRESH server: keep-alive RESETs every 30s ----
    # (fresh arcade: run1's closed card must not leak into run2)
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
        for i in range(5):
            g2.execute_action(ActionInput(id=GameAction.RESET, data={}))
            print(f"run2: keep-alive RESET {i + 1}/5", flush=True)
            time.sleep(30)
        status3, body3 = rest("GET", f"/api/scorecard/{card2}")
        print(
            f"run2: GET after keep-alives -> status={status3} body={body3[:200]} (expect 200)",
            flush=True,
        )
    finally:
        s2.stop()


if __name__ == "__main__":
    main()
