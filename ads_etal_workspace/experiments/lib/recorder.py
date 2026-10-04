"""RecorderPolicy: L0 exactly as shipped, plus it records what modules the L0 path never runs (shock
detection) into the per-run trace so X1 can score them offline against `World.truth`. It must not change a
single action; a test asserts its proposals equal `HTNToolsOnly`'s."""

from __future__ import annotations

from harness.policy import HTNToolsOnly, _log_actions
from harness.tools.shocks import detect_shocks


class RecorderPolicy(HTNToolsOnly):
    name = "l0_recorder"

    def __init__(self, params=None):
        super().__init__(params)
        self._action_log: dict = {}

    def recommend(self, obs):
        shocks = detect_shocks(obs, self.params, own_action_days=self._action_log)   # same call HTNHarness makes
        actions = super().recommend(obs)
        _log_actions(self._action_log, obs, actions)
        self.last_trace = dict(self.last_trace, shocks=shocks)
        return actions
