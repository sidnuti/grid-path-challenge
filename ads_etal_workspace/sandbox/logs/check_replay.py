"""python3 logs/check_replay.py -> compare every replayed Phase 2 run with its recording (identical outputs, $0 replay)."""
import filecmp, glob, json, os

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ok = bad = 0
print("Chimera R-C2 (CSV byte-identical):")
for rec in sorted(glob.glob(f"{R}/chimera/runs/results/rc2_full_*.csv")):
    rep = rec.replace("/results/", "/results_replay/")
    s = "MISSING" if not os.path.exists(rep) else ("identical" if filecmp.cmp(rec, rep, shallow=False) else "DIFFERENT")
    ok += s == "identical"; bad += s != "identical"
    print(f"  {os.path.basename(rec):58s} {s}")
print("MoHOLLM R-M1 (fvals + configs identical, 0 live calls):")
for line in open(f"{R}/logs/mohollm_jobs_replay.txt"):
    cfg, seed = line.split()
    tag = f"full_{os.path.basename(cfg)[:-5]}_s{seed}_qwen3.7-flash"
    a, b = f"{R}/mohollm/runs/work/{tag}/result.json", f"{R}/mohollm/runs/work_replay/{tag}/result.json"
    if not os.path.exists(b):
        s = "MISSING"
    else:
        x, y = json.load(open(a)), json.load(open(b))
        same = x["fvals"] == y["fvals"] and x["configs"] == y["configs"]
        s = "identical" if same and y["live_calls"] == 0 and y["cost"] == 0 else f"DIFFERENT (live {y['live_calls']}, ${y['cost']})"
    ok += s == "identical"; bad += s != "identical"
    print(f"  {tag:70s} {s}")
print(f"\n{ok} identical, {bad} not")
