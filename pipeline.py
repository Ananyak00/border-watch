"""Ingest (RTSP or file) -> YOLO + ByteTrack -> rules -> annotated frames + event log."""
import json, os, threading, time
import cv2
from rules import RuleEngine, foot, NAMES
from identity import IdentityGate

CLASSES = [0, 2, 3, 5, 7, 24, 26, 28]


class Pipeline:
    def __init__(self, cfg_path="config.json"):
        self.cfg_path = cfg_path
        self.cfg = json.load(open(cfg_path))
        self.engine = RuleEngine(self.cfg)
        self.ident = None
        if os.path.exists("known_faces.json") and self.cfg.get("identity", True):
            try:
                self.ident = IdentityGate(self.engine)
            except Exception as ex:
                print("identity module off:", ex)
        self.events, self.lock = [], threading.Lock()
        self.jpeg, self.running = None, False
        self.stats = {"fps": 0.0, "status": "idle", "frames": 0}
        self.model = None
        os.makedirs("snapshots", exist_ok=True)

    def save_cfg(self):
        json.dump(self.cfg, open(self.cfg_path, "w"), indent=2)

    def _load_model(self):
        if self.model is None:
            from ultralytics import YOLO
            self.model = YOLO(self.cfg["model"])

    def draw(self, frame, tracks):
        c = self.cfg
        if c.get("line"):
            cv2.line(frame, tuple(map(int, c["line"]["p1"])), tuple(map(int, c["line"]["p2"])), (0, 255, 255), 2)
        for key, col in (("buffer_zone", (255, 200, 0)), ("restricted_zone", (0, 0, 255))):
            if c.get(key):
                pts = cv2.convexHull(__import__("numpy").array(c[key], dtype="int32")) if False else \
                    __import__("numpy").array(c[key], dtype="int32")
                cv2.polylines(frame, [pts], True, col, 2)
        for tr in tracks:
            x1, y1, x2, y2 = map(int, tr["box"])
            bad = tr["id"] in self.engine.flagged
            col = (0, 0, 255) if bad else (0, 220, 0)
            cv2.rectangle(frame, (x1, y1), (x2, y2), col, 2)
            label = f"{NAMES.get(tr['cls'], tr['cls'])} #{tr['id']}"
            if self.ident:
                label = self.ident.label(tr["id"], label)
            if tr["id"] in self.engine.dwell_info:
                label += f" {self.engine.dwell_info[tr['id']]:.0f}s"
            cv2.putText(frame, label, (x1, max(15, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 2)
        return frame

    def run(self, source=None, log_path="events.jsonl", realtime=True):
        self._load_model()
        source = source or self.cfg["source"]
        cap = cv2.VideoCapture(int(source), cv2.CAP_DSHOW) if str(source).isdigit() else cv2.VideoCapture(source)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        fps = cap.get(cv2.CAP_PROP_FPS) or 25
        is_file = os.path.isfile(str(source))
        # --- frame skipping: run YOLO on about `process_fps` frames per second (files only) ---
        target = float(self.cfg.get("process_fps", 10))
        stride = max(1, round(fps / target)) if is_file else 1
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) if is_file else 0
        print(f"Processing {source}: {total} frames at {fps:.0f} FPS, analysing every {stride}th frame", flush=True)
        self.engine.reset()
        with self.lock:
            self.events = []
        log = open(log_path, "w")
        self.running, idx, t0, tick = True, 0, time.time(), time.time()
        done = 0
        last_proc = 0.0
        self.stats["status"] = "running"
        while self.running:
            ok = cap.grab()
            if not ok:
                if is_file and self.cfg.get("loop") and realtime:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    self.engine.reset(); self.model.predictor = None
                    idx, t0 = 0, time.time()
                    continue
                break
            if idx % stride or (not is_file and time.time() - last_proc < 1.0 / target):                      # skipped frame: keep the clock, do no work
                idx += 1
                continue
            last_proc = time.time()
            ok, frame = cap.retrieve()
            if not ok:
                idx += 1
                continue
            t_read = time.time()
            vt = idx / fps if is_file else t_read - t0       # rules run on video time
            r = self.model.track(frame, persist=True, tracker="bytetrack.yaml", verbose=False,
                                 conf=self.cfg["conf"], imgsz=self.cfg["imgsz"], classes=CLASSES)[0]
            tracks = []
            if r.boxes is not None and r.boxes.id is not None:
                for i, b, c, cf in zip(r.boxes.id.int().tolist(), r.boxes.xyxy.tolist(),
                                       r.boxes.cls.int().tolist(), r.boxes.conf.tolist()):
                    tracks.append(dict(id=i, box=b, cls=c, conf=cf))
            events = self.engine.update(tracks, vt)
            if self.ident:
                events = events + self.ident.update(frame, tracks, vt)
            latency_ms = (time.time() - t_read) * 1000       # frame read -> alert raised
            frame = self.draw(frame, tracks)
            for e in events:
                e["id"] = f"{int(time.time()*1000)}-{e['track_id']}"
                e["wall_time"] = time.strftime("%H:%M:%S")
                e["latency_ms"] = round(latency_ms, 1)
                e["snapshot"] = f"/snapshots/{e['id']}.jpg"
                cv2.imwrite(f"snapshots/{e['id']}.jpg", frame)
                log.write(json.dumps(e) + "\n"); log.flush()
                with self.lock:
                    self.events.append(e)
                print(f"  ALERT {e.get('type')} at video time {vt:.1f}s", flush=True)
            ok2, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ok2:
                self.jpeg = buf.tobytes()
            idx += 1
            done += 1
            self.stats["frames"] = idx
            if done % 10 == 0:
                self.stats["fps"] = round(10 / (time.time() - tick), 1); tick = time.time()
            if total and done % 25 == 0:
                print(f"  {idx}/{total} frames ({idx * 100 // total}%), {time.time() - t0:.0f}s elapsed", flush=True)
            if realtime and is_file:
                delay = t0 + idx / fps - time.time()
                if delay > 0:
                    time.sleep(delay)
        log.close(); cap.release()
        self.running, self.stats["status"] = False, "finished"