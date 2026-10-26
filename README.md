# border-watch
“Privacy-first intelligent surveillance on existing CCTV: real-time detection, tracking, and alerts.”
# Border-Watch: Privacy-First Surveillance on Existing CCTV

Real-time detection, tracking and context-aware alerts that run on
cameras you already have. No camera replacement needed.

## Features
- YOLOv8 person/object detection with object tracking
- Rules: line crossing, loitering, abandoned object, restricted-lane vehicle
- Live webcam/RTSP and recorded-clip modes in one dashboard
- Optional identity module (OpenCV YuNet + SFace) that flags unknown people
- Low-visibility testing (night, rain, fog)

## Results (site.mp4)
- Precision 1.0, recall 0.75, average latency about 100 ms
- Low-visibility: night and rain recall 0.75, fog recall 0.5

## How to run
1. pip install -r requirements.txt
2. Run start_system.bat
3. Open http://localhost:8000

## Demo video
Coming soon
