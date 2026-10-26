"""Live-camera helper. Usage:
python camera_tools.py go                       (patch, find camera, start everything)
python camera_tools.py list | use <index or URL> | preview | record <seconds> <name>"""
import json, os, sys, time
import cv2


def cap_for(s):
    s = str(s)
    c = cv2.VideoCapture(int(s), cv2.CAP_DSHOW) if s.isdigit() else cv2.VideoCapture(s)
    c.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return c


def use(v):
    cfg = json.load(open("config.json"))
    cfg["source"] = int(v) if str(v).isdigit() else v
    cfg["loop"] = False
    json.dump(cfg, open("config.json", "w"), indent=2)
    print("config.json source is now", cfg["source"])


def cameras():
    found = []
    for i in range(5):
        c = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        ok = c.isOpened() and c.read()[0]
        c.release()
        print("camera", i, "working" if ok else "not found")
        if ok:
            found.append(i)
    return found


def patch():
    p = open("pipeline.py").read()
    if "last_proc" in p:
        print("pipeline.py already patched")
        return
    reps = [
        ("cap = cv2.VideoCapture(source)\n",
         "cap = cv2.VideoCapture(int(source), cv2.CAP_DSHOW) if str(source).isdigit() else cv2.VideoCapture(source)\n        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)\n"),
        ("        done = 0\n", "        done = 0\n        last_proc = 0.0\n"),
        ("            if idx % stride:",
         "            if idx % stride or (not is_file and time.time() - last_proc < 1.0 / target):"),
        ("            ok, frame = cap.retrieve()\n", "            last_proc = time.time()\n            ok, frame = cap.retrieve()\n"),
    ]
    for a, b in reps:
        print("ok       " if a in p else "NOT FOUND", a.strip()[:45])
        p = p.replace(a, b)
    open("pipeline.py", "w").write(p)


cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
if cmd == "list":
    cameras()
elif cmd == "use":
    use(sys.argv[2])
elif cmd == "patch":
    patch()
elif cmd == "preview":
    cap = cap_for(json.load(open("config.json"))["source"])
    while True:
        ok, f = cap.read()
        if not ok:
            print("cannot read from the camera")
            break
        cv2.imshow("preview - press q to close", f)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
elif cmd == "record":
    secs, name = float(sys.argv[2]), sys.argv[3]
    cap = cap_for(json.load(open("config.json"))["source"])
    ok, f = cap.read()
    h, w = f.shape[:2]
    out = cv2.VideoWriter(f"videos/{name}.mp4", cv2.VideoWriter_fourcc(*"mp4v"), 20, (w, h))
    t0, n = time.time(), 0
    while time.time() - t0 < secs:
        ok, f = cap.read()
        if ok:
            while n < int((time.time() - t0) * 20):   # keep video time equal to real time
                out.write(f)
                n += 1
    out.release()
    print(f"saved videos/{name}.mp4")
elif cmd == "go":
    patch()
    cams = cameras()
    if not cams:
        print("No camera found. For a phone camera, run: python camera_tools.py use <video address>")
        sys.exit()
    use(cams[0])
    os.system("start start_system.bat")