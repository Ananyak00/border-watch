"""Optional identity module: name people from a local database and flag unknown people.
  python identity.py setup                    download face models + patch pipeline.py
  python identity.py snap "Rahul - Captain"   take an enrolment photo (stop the system first)
  python identity.py enroll                   build known_faces.json from known_people/
Photo names: "Name - Role.jpg" or "Name - Visitor - 2026-10-24.jpg" (visitor pass valid only that day)"""
import glob, json, os, sys, time, urllib.request
import cv2
import numpy as np

KNOWN_DIR, DB = "known_people", "known_faces.json"
BASE = "https://github.com/opencv/opencv_zoo/raw/main/models/"
MODELS = {"models/face_detection_yunet_2023mar.onnx": BASE + "face_detection_yunet/face_detection_yunet_2023mar.onnx",
          "models/face_recognition_sface_2021dec.onnx": BASE + "face_recognition_sface/face_recognition_sface_2021dec.onnx"}
DET, REC = list(MODELS)


def _models():
    return cv2.FaceDetectorYN.create(DET, "", (320, 320), 0.6, 0.3, 5000), cv2.FaceRecognizerSF.create(REC, "")


def embed(det, rec, img):
    h, w = img.shape[:2]
    det.setInputSize((w, h))
    _, faces = det.detect(img)
    if faces is None or len(faces) == 0:
        return None
    f = faces[np.argmax(faces[:, 2] * faces[:, 3])]
    return rec.feature(rec.alignCrop(img, f)).flatten()


class IdentityGate:
    def __init__(self, engine, thr=0.363, unknown_after=5.0, every=1.0):
        self.engine, self.thr, self.unknown_after, self.every = engine, thr, unknown_after, every
        self.det, self.rec = _models()
        self.people = json.load(open(DB))
        for p in self.people:
            p["emb"] = np.array(p["emb"], dtype=np.float32)
        self.state = {}
        self.last_unknown = -999.0

    def _valid(self, p):
        return p["valid"] in (None, "", time.strftime("%Y-%m-%d"))

    def update(self, frame, tracks, t):
        events = []
        for tr in tracks:
            if tr["cls"] != 0:
                continue
            s = self.state.setdefault(tr["id"], dict(first=t, last=-9.0, who=None, expired=None, alerted=False))
            if s["who"] is None and t - s["last"] >= self.every:
                s["last"] = t
                x1, y1, x2, y2 = map(int, tr["box"])
                h, w = frame.shape[:2]
                crop = frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
                if crop.shape[0] > 40 and crop.shape[1] > 40:
                    e = embed(self.det, self.rec, crop)
                    if e is not None:
                        best, who = -1.0, None
                        for p in self.people:
                            sc = float(np.dot(e, p["emb"]) / (np.linalg.norm(e) * np.linalg.norm(p["emb"]) + 1e-9))
                            if sc > best:
                                best, who = sc, p
                        if who is not None and best >= self.thr:
                            if self._valid(who):
                                s["who"] = who
                                events.append(dict(type="identified", severity="info", track_id=tr["id"], cls="person", t=t,
                                                   box=tr["box"], msg=f"{who['name']} ({who['role']}) recognised"))
                            else:
                                s["expired"] = who
            if s["who"] is None and not s["alerted"] and t - s["first"] >= self.unknown_after:
                s["alerted"] = True
                self.engine.flagged.add(tr["id"])
                why = f"expired visitor pass ({s['expired']['name']})" if s["expired"] else "not in the database"
                if t - self.last_unknown >= 30:
                    self.last_unknown = t
                    events.append(dict(type="unknown_person", severity="high", track_id=tr["id"], cls="person", t=t,
                                   box=tr["box"], msg=f"HIGH ALERT: person #{tr['id']} {why}"))
        return events

    def label(self, tid, default):
        s = self.state.get(tid)
        if not s:
            return default
        if s["who"]:
            return f"{s['who']['name']} ({s['who']['role']})"
        return "UNKNOWN" if s["alerted"] else default + " verifying"


def download():
    os.makedirs("models", exist_ok=True)
    for path, url in MODELS.items():
        if not os.path.exists(path) or os.path.getsize(path) < 100000:
            print("downloading", path)
            urllib.request.urlretrieve(url, path)
        print(path, os.path.getsize(path) // 1024, "KB")


def patch():
    p = open("pipeline.py").read()
    if "IdentityGate" in p:
        print("pipeline.py already patched")
        return
    reps = [
        ("from rules import RuleEngine, foot, NAMES\n", "from rules import RuleEngine, foot, NAMES\nfrom identity import IdentityGate\n"),
        ("        self.engine = RuleEngine(self.cfg)\n",
         '''        self.engine = RuleEngine(self.cfg)
        self.ident = None
        if os.path.exists("known_faces.json"):
            try:
                self.ident = IdentityGate(self.engine)
            except Exception as ex:
                print("identity module off:", ex)
'''),
        ("            events = self.engine.update(tracks, vt)\n",
         "            events = self.engine.update(tracks, vt)\n            if self.ident:\n                events = events + self.ident.update(frame, tracks, vt)\n"),
        ('''            label = f"{NAMES.get(tr['cls'], tr['cls'])} #{tr['id']}"\n''',
         '''            label = f"{NAMES.get(tr['cls'], tr['cls'])} #{tr['id']}"\n            if self.ident:\n                label = self.ident.label(tr["id"], label)\n'''),
    ]
    for a, b in reps:
        print("ok       " if a in p else "NOT FOUND", a.strip()[:45])
        p = p.replace(a, b)
    open("pipeline.py", "w").write(p)


def snap(name):
    src = json.load(open("config.json"))["source"]
    cap = cv2.VideoCapture(int(src), cv2.CAP_DSHOW) if str(src).isdigit() else cv2.VideoCapture(src)
    os.makedirs(KNOWN_DIR, exist_ok=True)
    while True:
        ok, f = cap.read()
        if not ok:
            print("cannot read from the camera")
            break
        cv2.imshow("SPACE = save photo, q = quit", f)
        k = cv2.waitKey(1) & 0xFF
        if k == 32:
            cv2.imwrite(f"{KNOWN_DIR}/{name}.jpg", f)
            print("saved", name)
            break
        if k == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()


def enroll():
    det, rec = _models()
    people = []
    for path in sorted(glob.glob(os.path.join(KNOWN_DIR, "*.*"))):
        parts = [x.strip() for x in os.path.splitext(os.path.basename(path))[0].split(" - ")]
        img = cv2.imread(path)
        e = embed(det, rec, img) if img is not None else None
        if e is None:
            print("no face found in", path)
            continue
        people.append(dict(name=parts[0], role=parts[1] if len(parts) > 1 else "Staff",
                           valid=parts[2] if len(parts) > 2 else None, emb=e.tolist()))
        print("enrolled", parts)
    json.dump(people, open(DB, "w"))
    print(len(people), "people saved to", DB)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "setup":
        download()
        patch()
    elif cmd == "snap":
        snap(sys.argv[2])
    elif cmd == "enroll":
        enroll()
    else:
        print(__doc__)