"""Named arms -> zero-arg policy factories. One place, so every experiment means the same thing by
'baseline', 'l0' or 'no_headroom_gate'."""

from __future__ import annotations

from gpc.policy import DeterministicTraversal, NoOpPolicy

from harness.policy import HTNToolsOnly

from .switchable_policy import ARMS as SWITCH_ARMS, PARAM_ARMS, STATE_ARMS, SwitchablePolicy, make_params, Switches


def factory(arm: str):
    if arm == "no_op":
        return NoOpPolicy
    if arm == "baseline":
        return DeterministicTraversal
    if arm == "l0":
        return HTNToolsOnly
    if arm == "l0rec":
        from .recorder import RecorderPolicy
        return RecorderPolicy
    if arm in SWITCH_ARMS:
        sw = SWITCH_ARMS[arm]
        return lambda: SwitchablePolicy(sw)
    if arm in PARAM_ARMS:
        kw = PARAM_ARMS[arm]
        return lambda: SwitchablePolicy(Switches(), make_params(**kw))
    if arm in STATE_ARMS:
        sm = STATE_ARMS[arm]
        return lambda: SwitchablePolicy(Switches(), make_params(min_allowance=0.0), sm)
    raise KeyError(arm)


FREE_ARMS = ["no_op", "baseline", "l0"] + [a for a in SWITCH_ARMS if a != "full"]


# ── X5 scripted-LLM arms:  llm_<params>_<leaf|all>_<mode>   params = default | recal ───────────────
LLM_LEAF_TAGS = {"L1": "L1_value", "L2": "L2_shock", "L3": "L3_sibling", "L4": "L4_explore", "L6": "L6_review"}


def llm_arm_parts(arm: str):
    _, pset, leaf, mode = arm.split("_", 3)
    leaves = tuple(LLM_LEAF_TAGS.values()) if leaf == "all" else (LLM_LEAF_TAGS[leaf],)
    return pset, leaves, mode


def llm_factory(arm: str, seed: int, scenario: str = "dev"):
    """Zero-arg policy factory for a scripted-LLM arm. Params: `default` = harness defaults at depth L2;
    `recal` = explore on (5 cells, 1000 INR/day cap) and review threshold 300, the recalibration the
    earlier runtime report suggested."""
    from dataclasses import replace

    from gpc.world import build_world
    from harness.config import load_params
    from .scripted_llm import DayAwareHarness, ScriptedLLM

    pset, leaves, mode = llm_arm_parts(arm)

    def make():
        w = build_world(seed, scenario)
        p = replace(load_params(), depth="L2")
        if pset == "recal":
            p = replace(p, explore_enabled=True, explore_max_thin_cells=5, explore_spend_cap_inr_day=1000.0,
                        llm_review_threshold_inr=300.0)
        llm = ScriptedLLM(w, mode, leaves, seed=seed)
        llm.attach_start_bids(w)
        return DayAwareHarness(p, llm=llm)
    return make


# ── X8 L2′ arms:  l2p_<aug|nat>_<rules|random|oracle|llm>[_r<k>]   and  l12_llm_r<k> ─────────────────────
L2P_ARMS_FREE = ["l2p_aug_rules", "l2p_nat_rules", "l2p_aug_random", "l2p_nat_random", "l2p_aug_oracle", "l2p_nat_oracle"]


def l2p_factory(arm: str, seed: int, scenario: str = "dev"):
    """Zero-arg policy factory for an L2′ arm (or the real-LLM L1/L2 comparison arm `l12_llm_r<k>`).
    `l2pv2_*` names run the same package after the revision-2 fixes (prompt v2, protected cuts, share-curve
    pricing, campaign holds block budget only); the prefix only keeps their cached results apart from v1's."""
    from dataclasses import replace

    from gpc.world import build_world
    from harness.config import load_params

    parts = arm.split("_")
    rep = int(parts[-1][1:]) if parts[-1].startswith("r") and parts[-1][1:].isdigit() else 0
    if arm.startswith("l12_llm"):
        from harness.policy import HTNHarness
        # per-run cap set high on purpose: the harness Meter prices qwen at its $3/$15 fallback (~100x real), so a
        # tight cap would silently default leaves; the X8 spend ledger (repriced from tokens) is the real guard
        return lambda: HTNHarness(replace(load_params(), depth="L2", llm_max_usd_per_run=5.0), replicate=rep)

    from harness_l2p.policy import L2PHarness
    from .scripted_l2p import OraclePlanner, RandomPlanner
    merge = {"aug": "augment", "nat": "native"}[parts[1]]
    kind = parts[2]
    params = replace(load_params(), llm_max_usd_per_run=0.25)

    def make():
        if kind == "rules":
            planner = "rules"
        elif kind == "random":
            planner = RandomPlanner(seed)
        elif kind == "oracle":
            planner = OraclePlanner(build_world(seed, scenario))
        elif kind == "llm":
            planner = "llm"
        else:
            raise KeyError(arm)
        return L2PHarness(params, planner=planner, merge=merge, replicate=rep, name=arm)
    return make
