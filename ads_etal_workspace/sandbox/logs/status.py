"""python logs/status.py  -> progress of the Phase 2 runs (reads ledger + run outputs; touches nothing)."""
import collections, glob, json, os, time
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
es = [json.loads(l) for l in open(f"{R}/ledger.jsonl")]
by = collections.defaultdict(lambda: [0, 0, 0.0, 0])
for e in es:
    k = e["note"] or e["item"]; b = by[k]; b[0] += 1; b[1] += e["cached"]; b[2] += e["cost_usd"]; b[3] = e["ts"]
tot = collections.defaultdict(float)
for e in es: tot[e["item"]] += e["cost_usd"]
print({k: round(v, 3) for k, v in tot.items()}, "TOTAL $%.3f / 25" % sum(tot.values()))
print("\nChimera R-C2 (agent runs; calls so far, cost, last-call age):")
for k, b in sorted(by.items()):
    if k.startswith("rc2_full"): print(f"  {k[9:]:48s} calls {b[0]:4d} ${b[2]:.3f}  {int(time.time()-b[3]):4d}s ago")
done = sorted(glob.glob(f"{R}/chimera/runs/results/rc2_full_*.csv")); print("  finished arms:", len(done), "/ 18")
print("\nMoHOLLM R-M1 (qwen), the 16 jobs in logs/mohollm_jobs.txt (2 seeds x 4 problems x 2 methods):")
jobs = [l.split() for l in open(f"{R}/logs/mohollm_jobs.txt") if l.strip()]
tags = [f"full_{os.path.basename(c)[:-5]}_s{sd}_qwen3.7-flash" for c, sd in jobs]
fin = {t for t in tags if os.path.exists(f"{R}/mohollm/runs/work/{t}/result.json")}
for t in tags:
    b = by.get(t); state = "DONE" if t in fin else "run "
    print(f"  {t[5:]:60s} {state} " + (f"calls {b[0]:4d} ${b[2]:.3f} {int(time.time()-b[3]):5d}s ago" if b else "not started"))
print("  finished:", len(fin), "/", len(tags), "| cancelled seed-6790 job excluded")
