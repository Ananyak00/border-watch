from pydantic import BaseModel
import asyncio, json, threading, time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pipeline import Pipeline

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
pipe = Pipeline()
import os; os.makedirs("snapshots", exist_ok=True)
app.mount("/snapshots", StaticFiles(directory="snapshots"), name="snapshots")


@app.on_event("startup")
def start():
    threading.Thread(target=pipe.run, daemon=True).start()


@app.get("/video")
def video():
    def gen():
        while True:
            if pipe.jpeg:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + pipe.jpeg + b"\r\n"
            time.sleep(0.04)
    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/events")
def events():
    with pipe.lock:
        return pipe.events


@app.get("/api/stats")
def stats():
    with pipe.lock:
        lat = [e["latency_ms"] for e in pipe.events]
    return {**pipe.stats, "alerts": len(lat),
            "avg_latency_ms": round(sum(lat) / len(lat), 1) if lat else 0,
            "max_latency_ms": max(lat) if lat else 0}


@app.get("/api/config")
def get_config():
    return pipe.cfg


@app.post("/api/config")
async def set_config(req: Request):
    pipe.cfg.update(await req.json())       # live update: the engine reads the same dict
    pipe.save_cfg()
    return {"ok": True}

from pydantic import BaseModel

class MockAlert(BaseModel):
    type: str = "line_crossing"
    t: float = 12.0
    latency_ms: float = 42.0

@app.post("/api/alert")
def trigger_mock_alert(alert: MockAlert):
    with pipe.lock:
        pipe.events.append(alert.dict())
    return {"status": "success", "event": alert.dict()}
class MockAlert(BaseModel):
    type: str = "line_crossing"
    t: float = 12.0
    latency_ms: float = 42.0

@app.post("/api/alert")
def trigger_mock_alert(alert: MockAlert):
    with pipe.lock:
        pipe.events.append(alert.model_dump() if hasattr(alert, "model_dump") else alert.dict())
    return {"status": "success", "event": alert.model_dump() if hasattr(alert, "model_dump") else alert.dict()}
@app.websocket("/ws")
async def ws(sock: WebSocket):
    await sock.accept()
    sent = 0
    try:
        while True:
            with pipe.lock:
                new, sent = pipe.events[sent:], len(pipe.events)
            for e in new:
                await sock.send_json(e)
            await asyncio.sleep(0.2)
    except WebSocketDisconnect:
        pass
