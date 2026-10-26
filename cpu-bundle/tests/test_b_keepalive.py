"""Test B — validate the staged startup keep-alive patch on CPU, end to end.

Runs the REAL patched HarnessSolver (solver.patched.py as solver.py) against a
local competition-mode arcade with STALE_MINUTES=1, while the analyzer NEVER
answers (startup starvation, like the dry-run's 900s ConnectionError loop).

Two runs:
  B1 control:  keep-alive disabled  (ARC3_STARTUP_KEEPALIVE_SECONDS=0).
       Expect: shared scorecard auto-closes ~60s in; games stall; keep-alive
       lines absent from the log.
  B2 patched:  keep-alive forced on (FORCE=1, interval 30s, max 6).
       Expect: "startup keep-alive RESET" lines in the log; scorecard still
       open while games stall.

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
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

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


class StarvingAnalyzer:
    """Never answers: mimics a model server still loading weights."""

    total_tokens = 0

    def __init__(self):
        self.calls = 0

    def analyze(self, *args, **kwargs):
        self.calls += 1
        time.sleep(5)
        return SimpleNamespace(
            retryable_failure=True, yielded_control=False, step_executed=False
        )


def run_once(*, keepalive: bool, workdir: Path, game_ids, server_base_url):
    if keepalive:
        os.environ["ARC3_STARTUP_KEEPALIVE_FORCE"] = "1"
        os.environ["ARC3_STARTUP_KEEPALIVE_SECONDS"] = "30"
        os.environ["ARC3_STARTUP_KEEPALIVE_MAX_EVENTS"] = "6"
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


def main():
    env_files = os.environ["ENV_FILES"]
    ids = discover_ids(3)
    server = competition_arcade.CompetitionArcadeServer(
        game_ids=ids,
        environments_dir=env_files,
    ).start()
    try:
        game_ids = server.exposed_game_ids[:3]
        print(f"server up, using {game_ids}", flush=True)
        with tempfile.TemporaryDirectory(prefix="cpu-b1-") as d1:
            card1 = run_once(
                keepalive=False,
                workdir=Path(d1),
                game_ids=game_ids,
                server_base_url=server.base_url,
            )
            print(f"B1 control done, card was {card1}", flush=True)
        with tempfile.TemporaryDirectory(prefix="cpu-b2-") as d2:
            card2 = run_once(
                keepalive=True,
                workdir=Path(d2),
                game_ids=game_ids,
                server_base_url=server.base_url,
            )
            print(f"B2 keepalive done, card was {card2}", flush=True)
        print(
            "Compare: B1 log should have NO 'startup keep-alive RESET' lines "
            "(card auto-closed ~60s in); B2 log should show them every ~30s.",
            flush=True,
        )
    finally:
        server.stop()


if __name__ == "__main__":
    main()
