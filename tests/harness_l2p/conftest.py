import pytest

from gpc.policy import DeterministicTraversal, Policy
from gpc.runner import simulate
from gpc.world import build_world


class _Capture(Policy):
    name = "capture"

    def __init__(self):
        self.obs, self.inner = [], DeterministicTraversal()

    def recommend(self, obs):
        self.obs.append(obs)
        self.last_trace = {}
        return self.inner.recommend(obs)


@pytest.fixture(scope="session")
def observations():
    """Real observations for runs 1-3 of dev seed 7 (baseline trajectory)."""
    p = _Capture()
    simulate(build_world(7), p, n_runs=3)
    return p.obs


@pytest.fixture(scope="session")
def ctx(observations):
    from harness.config import load_params
    from harness.tools.features import diagnose
    from harness.tools.incrementality import iota_lookup
    from harness_l2p.brief import build_brief
    obs = observations[2]
    params = load_params()
    diag = diagnose(obs)
    iota = iota_lookup(obs)
    return {"obs": obs, "params": params, "diag": diag, "iota": iota, "brief": build_brief(obs, diag, iota, params)}
