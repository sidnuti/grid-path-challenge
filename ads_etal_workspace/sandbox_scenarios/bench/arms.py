"""Non-LLM arms and the in-space oracle on the Track-A black box (design/04 §3.1, §2.4). All $0.

    python -m bench.arms --arm A1 --scenario sc1_cannibal --seed 7 --evals 50
    python -m bench.arms --arm O1 --scenario sc1_cannibal --seed 7 --evals 2000 --workers 8

  A0  starting set-up held (no-op, guardrail-free) and the legacy `deterministic_traversal` policy (with guardrails)
  A1  Sobol search: the shared initial design extended along the same scrambled sequence
  A2  BoTorch: SingleTaskGP + qLogExpectedImprovement (G0) / qLogNoisyExpectedHypervolumeImprovement (G1), q = 1,
      starting from the shared initial design
  O1  CMA-ES on IncRev (G0), restarts with increasing population (IPOP) until the budget is used, from the centre

Every arm writes `results/p3/<arm>/<scenario>_<goal>_s<seed>.json` with every evaluation in order.
"""
from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from .blackbox import BlackBox
from .decode import Encoding
from .design import N_INIT, initial_design, sobol

RESULTS = Path(__file__).resolve().parents[1] / "results" / "p3"
_BB: dict = {}


def _bb(scenario, seed, budget_scale) -> BlackBox:
    k = (scenario, seed, budget_scale)
    if k not in _BB:
        _BB[k] = BlackBox(scenario, seed, Encoding(budget_scale=budget_scale))
    return _BB[k]


def _eval(args):
    scenario, seed, budget_scale, x = args
    return _bb(scenario, seed, budget_scale)(x)


class Evaluator:
    def __init__(self, scenario, seed, goal, workers=1):
        self.scenario, self.seed, self.goal = scenario, seed, goal
        self.bs = goal == "G1"
        self.enc = Encoding(budget_scale=self.bs)
        self.workers = workers
        self.pool = ProcessPoolExecutor(workers) if workers > 1 else None
        self.log: list[dict] = []

    def __call__(self, X) -> list[dict]:
        X = [np.clip(np.asarray(x, float), 0, 1) for x in X]
        jobs = [(self.scenario, self.seed, self.bs, x) for x in X]
        out = list(self.pool.map(_eval, jobs)) if self.pool else [_eval(j) for j in jobs]
        self.log.extend(out)
        return out

    def close(self):
        if self.pool:
            self.pool.shutdown()


def objectives(r: dict, goal: str) -> list[float]:
    if goal == "G0":
        return [r["inc_rev"] / 1e5]
    st = r["f3_s6_sell_through"]
    return [r["inc_rev"] / 1e5, 100 * r["f2_s5_north_slot1"], 100 * st if st == st else 0.0]


# ── arms ───────────────────────────────────────────────────────────────────────
def arm_a0(ev: Evaluator) -> dict:
    from gpc.policy import DeterministicTraversal
    from gpc.runner import simulate
    from gpc.world import build_world
    from .goals import measure
    from .sim import run
    bb = _bb(ev.scenario, ev.seed, ev.bs)
    hold = measure(bb.world, run(bb.ws, lambda obs: (obs.public["campaigns"], obs.public["campaign_keywords"]),
                                 name="hold"), bb.budget_per_day())
    w = build_world(ev.seed, ev.scenario)
    trav = measure(w, simulate(w, DeterministicTraversal()), bb.budget_per_day())
    return {"hold": hold, "traversal": trav}


def arm_a1(ev: Evaluator, evals: int):
    ev(sobol(ev.enc.d, evals, ev.seed))


def arm_a2(ev: Evaluator, evals: int):
    import torch
    from botorch.acquisition.logei import qLogExpectedImprovement
    from botorch.acquisition.multi_objective.logei import qLogNoisyExpectedHypervolumeImprovement
    from botorch.fit import fit_gpytorch_mll
    from botorch.models import SingleTaskGP
    from botorch.models.transforms import Normalize, Standardize
    from botorch.optim import optimize_acqf
    from botorch.utils.multi_objective.box_decompositions.dominated import DominatedPartitioning  # noqa: F401
    from gpytorch.mlls import ExactMarginalLogLikelihood

    torch.manual_seed(ev.seed)
    d = ev.enc.d
    bounds = torch.stack([torch.zeros(d), torch.ones(d)]).double()
    X = [np.asarray(x) for x in initial_design(d, ev.seed, N_INIT)]
    Y = [objectives(r, ev.goal) for r in ev(X)]
    while len(X) < evals:
        tx, ty = torch.tensor(np.array(X)).double(), torch.tensor(np.array(Y)).double()
        model = SingleTaskGP(tx, ty, input_transform=Normalize(d), outcome_transform=Standardize(ty.shape[-1]))
        fit_gpytorch_mll(ExactMarginalLogLikelihood(model.likelihood, model))
        if ev.goal == "G0":
            acq = qLogExpectedImprovement(model, best_f=ty.max())
        else:
            ref = ty.min(0).values - 0.1 * (ty.max(0).values - ty.min(0).values).clamp_min(1e-6)
            acq = qLogNoisyExpectedHypervolumeImprovement(model, ref_point=ref.tolist(), X_baseline=tx,
                                                          prune_baseline=True)
        cand, _ = optimize_acqf(acq, bounds=bounds, q=1, num_restarts=10, raw_samples=256)
        x = np.round(cand.detach().numpy()[0], 6)
        X.append(x)
        Y.append(objectives(ev([x])[0], ev.goal))


def arm_o1(ev: Evaluator, evals: int, sigma0: float = 0.3):
    import cma
    assert ev.goal == "G0", "O1 is the E1 in-space oracle"
    d, used, k = ev.enc.d, 0, 0
    pop = None
    while used < evals:
        es = cma.CMAEvolutionStrategy([0.5] * d, sigma0, {"bounds": [0, 1], "seed": ev.seed + k, "verbose": -9,
                                                          **({"popsize": pop} if pop else {})})
        pop = es.popsize
        while not es.stop() and used < evals:
            X = es.ask()
            X = X[: max(1, evals - used)]
            R = ev(X)
            used += len(X)
            if len(X) < es.popsize:
                break
            es.tell(X, [-r["inc_rev"] for r in R])
        k += 1
        pop *= 2                                    # IPOP restart


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=["A0", "A1", "A2", "O1"])
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--goal", default="G0", choices=["G0", "G1"])
    ap.add_argument("--evals", type=int, default=50)
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args()
    ev = Evaluator(a.scenario, a.seed, a.goal, a.workers)
    t0 = time.time()
    extra = {}
    if a.arm == "A0":
        extra = arm_a0(ev)
    elif a.arm == "A1":
        arm_a1(ev, a.evals)
    elif a.arm == "A2":
        arm_a2(ev, a.evals)
    else:
        arm_o1(ev, a.evals)
    ev.close()
    out = RESULTS / a.arm
    out.mkdir(parents=True, exist_ok=True)
    rec = {"arm": a.arm, "scenario": a.scenario, "seed": a.seed, "goal": a.goal, "evals_budget": a.evals,
           "n_evals": len(ev.log), "secs": round(time.time() - t0, 1), "evaluations": ev.log, **extra}
    (out / f"{a.scenario}_{a.goal}_s{a.seed}.json").write_text(json.dumps(rec, default=float))
    best = max((e["inc_rev"] for e in ev.log), default=None)
    print("RESULT", {k: v for k, v in rec.items() if k not in ("evaluations", "hold", "traversal")},
          "best_inc_rev", best and round(best),
          {k: round(extra[k]["inc_rev"]) for k in extra} if extra else "")


if __name__ == "__main__":
    main()
