"""Batch-run clips headless and score them. Usage:
python run_offline.py videos/day.mp4 videos/night.mp4 videos/rain.mp4
Ground truth for videos/X.mp4 is expected at videos/X.csv (fallback: videos/<base>.csv without suffix)."""
import json, os, sys
from pipeline import Pipeline
from evaluate import evaluate

os.makedirs("results", exist_ok=True)
report = {}
for clip in sys.argv[1:]:
    name = os.path.splitext(os.path.basename(clip))[0]
    p = Pipeline()
    p.cfg["loop"] = False
    log = f"results/{name}.jsonl"
    p.run(source=clip, log_path=log, realtime=False)
    gt = f"videos/{name}.csv"
    if not os.path.exists(gt):
        gt = "videos/day.csv"    # degraded clips share the day clip's ground truth
    report[name] = evaluate(log, gt)
    print(name, json.dumps(report[name]))
json.dump(report, open("results/report.json", "w"), indent=2)
