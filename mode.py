"""Switch between the recorded clip and the live camera without losing either setup.
  python mode.py clip     recorded clip (videos/site.mp4), identity off
  python mode.py live     live camera, identity on"""
import json, os, shutil, sys


def is_live(cfg):
    s = str(cfg.get("source"))
    return s.isdigit() or s.startswith("rtsp")


def patch():
    p = open("pipeline.py").read()
    old = 'if os.path.exists("known_faces.json"):'
    if old in p and 'cfg.get("identity"' not in p:
        open("pipeline.py", "w").write(p.replace(old, 'if os.path.exists("known_faces.json") and self.cfg.get("identity", True):'))
        print("pipeline.py: identity switch added")


mode = sys.argv[1] if len(sys.argv) > 1 else ""
if mode not in ("clip", "live"):
    sys.exit(__doc__)
cur = json.load(open("config.json"))
shutil.copy("config.json", "config_live.json" if is_live(cur) else "config_clip.json")   # keep the setup we are leaving
target = "config_live.json" if mode == "live" else "config_clip.json"
if not os.path.exists(target):
    if mode == "clip" and os.path.exists("config_backup.json"):
        target = "config_backup.json"
    else:
        sys.exit("No saved setup for this mode yet: " + target)
cfg = json.load(open(target))
if mode == "clip":
    cfg["source"], cfg["loop"], cfg["identity"] = "videos/site.mp4", True, False
else:
    cfg["identity"] = True
json.dump(cfg, open("config.json", "w"), indent=2)
patch()
print("config.json is now the", mode, "setup (source:", cfg["source"], ")")