"""Test B — validate the staged startup keep-alive patch on CPU, end to end.

Runs the REAL patched HarnessSolver (solver.patched.py as solver.py) against a
local competition-mode arcade with STALE_MINUTES=1, while the analyzer NEVER
answers (startup starvation, like the dry-run's 900s ConnectionError loop).

Two runs, each on a FRESH server (the gateway allows one scorecard lifetime
per arcade):
  B1 control:  keep-alive disabled  (ARC3_STARTUP_KEEPALIVE_SECONDS=0).
       Expect: games stall and give_up at 0.00; log has NO
       'startup keep-alive RESET' lines.
  B2 patched:  keep-alive forced on (FORCE=1, interval 30s->clamped 60s,
       max 3 events).
       Expect: 'startup keep-alive RESET ... issued' lines in the log;
       scorecard still open (GET 200) while games stall.

Starvation model: the stub analyzer RAISES ConnectionError (it never
returns). Returning a retryable_failure would trip the solver's
"analyzer contact" tripwire and stop the keep-alive — the dry-run log
shows ConnectionError retries, so raising is the faithful model.

Needs (Kaggle CPU notebook, internet ON):
  pip install arc-agi arcengine flask pydantic requests
Env:
  ENV_FILES = path to the competition `environment_files` dir
  CPU_BUNDLE = unzipped cpu_bundle.zip from the assistant (contains the
               patched trees + these scripts under /kaggle/working/cpu_bundle)

Usage:
  python test_b_keepalive.py
"""

import asyncio
import json
import os
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

# MUST precede any arc_agi import: the idle timeout is read at import time.
os.environ["STALE_MINUTES"] = "1"
os.environ.setdefault("ARC_API_KEY", "test-key-123")
os.environ.setdefault("ARC3_MAX_ACTIVE_STREAMS", "3")
os.environ.setdefault("ARC3_MAX_ANALYZER_FAILURES", "-1")  # never give up; stall
os.environ.setdefault("ARC3_WARMUP_ACTION_GAMES", "1")

BUNDLE = Path(os.environ.get("CPU_BUNDLE", "/kaggle/working/cpu_bundle"))
sys.path.insert(0, str(BUNDLE / "taaf-src"))
sys.path.insert(0, str(BUNDLE / "ARC3-Inference"))

from taaf import competition_arcade  # noqa: E402
from taaf.game import RunSession  # noqa: E402
from taaf.game_api import ArcadeSpec, GameAPI  # noqa: E402
import arc_agi  # noqa: E402
from inference.framework.solver import HarnessSolver  # noqa: E402

API_KEY = os.environ.get("ARC_API_KEY", "test-key-123")


class StarvingAnalyzer:
    """Never answers: raises like a model server still loading weights.

    Must RAISE (ConnectionError, as in the dry-run log), not return a
    retryable failure: any returned result trips the solver's first-contact
    tripwire and stops the keep-alive task.
    """

    total_tokens = 0

    def __init__(self):
        self.calls = 0

    def analyze(self, *args, **kwargs):
        self.calls += 1
        time.sleep(5)
        raise ConnectionError("model server still loading (stub starvation)")


def run_once(*, keepalive: bool, workdir: Path, game_ids, server_base_url):
    if keepalive:
        os.environ["ARC3_STARTUP_KEEPALIVE_FORCE"] = "1"
        os.environ["ARC3_STARTUP_KEEPALIVE_SECONDS"] = "30"  # clamped to 60s floor
        os.environ["ARC3_STARTUP_KEEPALIVE_MAX_EVENTS"] = "3"
    else:
        os.environ["ARC3_STARTUP_KEEPALIVE_FORCE"] = "0"
        os.environ["ARC3_STARTUP_KEEPALIVE_SECONDS"] = "0"

    # Re-read env-gated module constants (imported once per process).
    import inference.framework.solver as solver_mod

    solver_mod.STARTUP_KEEPALIVE_SECONDS = float(
        os.environ.get("ARC3_STARTUP_KEEPALIVE_SECONDS", "0")
    )
    solver_mod.STARTUP_KEEPALIVE_FORCE = (
        os.environ.get("ARC3_STARTUP_KEEPALIVE_FORCE", "0").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    solver_mod.STARTUP_KEEPALIVE_MAX_EVENTS = int(
        os.environ.get("ARC3_STARTUP_KEEPALIVE_MAX_EVENTS", "6")
    )

    spec = ArcadeSpec(
        operation_mode=arc_agi.OperationMode.COMPETITION,
        arc_base_url=server_base_url,
        environments_dir="",
    )
    session = RunSession()
    games = []
    for gid in game_ids:
        game = GameAPI(env_name=gid, arcade_spec=spec)
        game.start_game(session)
        games.append(game)
    card = games[0]._scorecard_id

    solver = HarnessSolver(
        concurrency=3,
        max_runtime_s_per_game=200,
        analyzer_timeout=30.0,
    )
    solver.analyzer_factory = lambda game, index: StarvingAnalyzer()
    solver.job_dir = workdir
    solver.setup()
    asyncio.run(solver.run_games(games))
    return card


def discover_ids(n):
    """List local env game IDs without re_arc (official_game_ids needs it)."""
    import logging

    env_dir = os.environ["ENV_FILES"]
    probe = arc_agi.Arcade(
        operation_mode=arc_agi.OperationMode.OFFLINE,
        environments_dir=env_dir,
        logger=logging.getLogger("cpu-probe"),
    )
    ids = [env.game_id for env in probe.available_environments]
    print(f"probe: {len(ids)} envs, sample {ids[:5]}", flush=True)
    assert len(ids) >= n, f"need >={n} envs, found {len(ids)}"
    return ids[:n]


def get_card(base_url, card_id, timeout=15):
    url = base_url + f"/api/scorecard/{card_id}"
    req = urllib.request.Request(
        url, headers={"X-API-Key": API_KEY}, method="GET"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return -1, repr(exc)


def main():
    env_files = os.environ["ENV_FILES"]
    ids = discover_ids(3)
    # Fresh server per phase: the gateway arcade allows one scorecard
    # lifetime, so B1's closed/conflicted card must not leak into B2.
    s1 = competition_arcade.CompetitionArcadeServer(
        game_ids=ids,
        environments_dir=env_files,
    ).start()
    try:
        game_ids = s1.exposed_game_ids[:3]
        print(f"server up, using {game_ids}", flush=True)
        with tempfile.TemporaryDirectory(prefix="cpu-b1-") as d1:
            card1 = run_once(
                keepalive=False,
                workdir=Path(d1),
                game_ids=game_ids,
                server_base_url=s1.base_url,
            )
            print(f"B1 control done, card was {card1}", flush=True)
    finally:
        s1.stop()
    s2 = competition_arcade.CompetitionArcadeServer(
        game_ids=ids,
        environments_dir=env_files,
    ).start()
    try:
        game_ids2 = s2.exposed_game_ids[:3]
        with tempfile.TemporaryDirectory(prefix="cpu-b2-") as d2:
            card2 = run_once(
                keepalive=True,
                workdir=Path(d2),
                game_ids=game_ids2,
                server_base_url=s2.base_url,
            )
            print(f"B2 keepalive done, card was {card2}", flush=True)
            st, body = get_card(s2.base_url, card2)
            print(
                f"B2: GET card after stall -> status={st} body={body[:200]} (expect 200)",
                flush=True,
            )
        print(
            "Compare: B1 log should have NO 'startup keep-alive RESET' lines; "
            "B2 log should show them ~every 60s.",
            flush=True,
        )
    finally:
        s2.stop()


if __name__ == "__main__":
    main()
