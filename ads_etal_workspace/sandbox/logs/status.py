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
print("\nMoHOLLM R-M1 (qwen):")
fin = {os.path.basename(os.path.dirname(f)) for f in glob.glob(f"{R}/mohollm/runs/work/full_*/result.json")}
for k, b in sorted(by.items()):
    if k.startswith("full_"): print(f"  {k[5:]:60s} {'DONE' if k in fin else 'run '} calls {b[0]:4d} ${b[2]:.3f} {int(time.time()-b[3]):4d}s ago")
print("  finished:", len(fin), "/ 24")
