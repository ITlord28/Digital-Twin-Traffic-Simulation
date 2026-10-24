#!/usr/bin/env python3
"""
Digital Twin AI Engine Server
Backend service for Java Desktop Application (Digital Twin & ROI Traffic Pressure)
Provides:
  - Video stream (MJPEG): Combined HUD, Clean Digital Twin, Morphological Mask
  - Real-time telemetry JSON: Tracked vehicles, Digital Twin coordinates, ROI Pressure, Queue Length, Occupancy
  - REST API: Switch video sources, update ROI polygon dynamically, configure thresholds
"""

import os
import sys
import time
import json
import math
import collections
import threading
from typing import List, Dict, Any, Optional

import cv2
import numpy as np
import torch
from ultralytics import YOLO

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Device & Model Setup
# ---------------------------------------------------------------------------
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
print(f"[AI-ENGINE] Initializing on device: {DEVICE}")

DEFAULT_MODEL_PATH = os.path.join(BASE_DIR, "yolov8s.pt")
if not os.path.exists(DEFAULT_MODEL_PATH):
    DEFAULT_MODEL_PATH = os.path.join(BASE_DIR, "yolov8n.pt")

print(f"[AI-ENGINE] Loading model: {DEFAULT_MODEL_PATH}")
yolo_model = YOLO(DEFAULT_MODEL_PATH)

# Supported vehicle classes in COCO or custom
TARGET_VEHICLE_NAMES = {"car", "motorcycle", "motorbike", "bus", "truck"}

# ---------------------------------------------------------------------------
# State & Processor
# ---------------------------------------------------------------------------
class EngineState:
    def __init__(self):
        self.lock = threading.Lock()
        self.running = True
        self.paused = False
        
        # Video Source
        self.source_type = "preset"  # 'preset', 'file', 'webcam'
        self.source_path = os.path.join(BASE_DIR, "intersection_1_roi.mp4")
        self.camera_index = 0
        self.loop_video = True
        
        # Model config
        self.conf_threshold = 0.35
        self.dilation_kernel = 15
        self.pixel_to_meter = 0.05
        self.vehicle_body_length_m = 4.5
        self.queue_axis = "y"  # 'y' or 'x'
        self.dwelling_speed_thresh = 3.0  # px per frame
        self.dwelling_frames_thresh = 8
        
        # Default ROI points (normalized 0.0 - 1.0)
        self.roi_points_norm = [
            [0.44, 0.84],
            [0.61, 0.42],
            [0.22, 0.38],
            [0.00, 0.50],
            [0.00, 0.79]
        ]
        
        # Telemetry Cache
        self.fps = 0.0
        self.total_detected = 0
        self.class_counts = {"car": 0, "motorcycle": 0, "bus": 0, "truck": 0}
        self.vehicles_in_roi_count = 0
        self.occupancy_pct = 0.0
        self.queue_length_m = 0.0
        self.pressure_score = 0.0
        self.traffic_level = "NORMAL"  # NORMAL, MODERATE, CONGESTED
        self.tracked_vehicles: List[Dict[str, Any]] = []
        self.recent_history = collections.deque(maxlen=60)
        
        # Encoded Frames for Streaming
        self.latest_video_jpeg = None
        self.latest_clean_jpeg = None
        self.latest_mask_jpeg = None
        
        # Raw frames for snapshot
        self.latest_raw_frame = None
        
        # Tracking memory: track_id -> deque of recent positions
        self.track_history = collections.defaultdict(lambda: collections.deque(maxlen=25))
        self.track_dwell_counter = collections.defaultdict(int)

state = EngineState()

# ---------------------------------------------------------------------------
# Helper Geometry & Computer Vision Functions
# ---------------------------------------------------------------------------
def compute_stop_line(roi_polygon_px: np.ndarray, queue_axis: str) -> int:
    if len(roi_polygon_px) == 0:
        return 0
    if queue_axis == "y":
        return int(np.max(roi_polygon_px[:, 1]))
    else:
        return int(np.max(roi_polygon_px[:, 0]))

def calculate_morphological_occupancy(frame_shape, dwelling_vehicles, roi_polygon_px, kernel_size):
    h, w = frame_shape[:2]
    vehicle_mask = np.zeros((h, w), dtype=np.uint8)
    for v in dwelling_vehicles:
        x1, y1, x2, y2 = v["box"]
        # Clip to image boundary
        x1 = max(0, min(w - 1, x1))
        y1 = max(0, min(h - 1, y1))
        x2 = max(0, min(w - 1, x2))
        y2 = max(0, min(h - 1, y2))
        cv2.rectangle(vehicle_mask, (x1, y1), (x2, y2), 255, -1)

    # Dilation to group close vehicles
    k = max(3, kernel_size | 1)  # ensure odd integer
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
    dilated_mask = cv2.dilate(vehicle_mask, kernel, iterations=1)

    roi_mask = np.zeros((h, w), dtype=np.uint8)
    if len(roi_polygon_px) >= 3:
        cv2.fillPoly(roi_mask, [roi_polygon_px], 255)

    combined = cv2.bitwise_and(dilated_mask, roi_mask)
    roi_pixels = cv2.countNonZero(roi_mask)
    occupied_pixels = cv2.countNonZero(combined)

    occupancy = (occupied_pixels / roi_pixels * 100.0) if roi_pixels > 0 else 0.0
    return min(occupancy, 100.0), combined

def calculate_queue_length(dwelling_vehicles, stop_line_coord, queue_axis, pixel_to_meter, body_length):
    if len(dwelling_vehicles) == 0:
        return 0.0
    if queue_axis == "y":
        positions = [v["bottom_center"][1] for v in dwelling_vehicles]
    else:
        positions = [v["bottom_center"][0] for v in dwelling_vehicles]

    max_dist_px = max(abs(pos - stop_line_coord) for pos in positions)
    length_m = (max_dist_px * pixel_to_meter) + body_length
    return round(length_m, 2)

# ---------------------------------------------------------------------------
# Background Processing Worker
# ---------------------------------------------------------------------------
def video_worker():
    global yolo_model
    print("[AI-ENGINE] Video worker thread started.")
    
    cap = None
    current_source = None
    last_fps_time = time.time()
    frame_count = 0
    
    while state.running:
        # Determine source
        with state.lock:
            if state.source_type == "webcam":
                target_src = state.camera_index
            else:
                target_src = state.source_path
            paused = state.paused
            conf_thresh = state.conf_threshold
            kernel_sz = state.dilation_kernel
            p2m = state.pixel_to_meter
            q_axis = state.queue_axis
            body_len = state.vehicle_body_length_m
            roi_pts_norm = list(state.roi_points_norm)
            loop_vid = state.loop_video

        # Reopen capture if source changed or cap is None
        if cap is None or current_source != target_src:
            if cap is not None:
                cap.release()
            print(f"[AI-ENGINE] Opening capture: {target_src}")
            cap = cv2.VideoCapture(target_src)
            current_source = target_src
            if not cap.isOpened():
                print(f"[AI-ENGINE] Failed to open video source: {target_src}")
                time.sleep(1.0)
                continue

        if paused:
            time.sleep(0.05)
            continue

        ret, frame = cap.read()
        if not ret or frame is None:
            if state.source_type != "webcam" and loop_vid:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            else:
                time.sleep(0.1)
                continue

        # Downscale if too large for high throughput
        fh, fw = frame.shape[:2]
        if fw > 960:
            scale = 960.0 / fw
            frame = cv2.resize(frame, (960, int(fh * scale)))
            fh, fw = frame.shape[:2]

        # Calculate pixel ROI polygon
        roi_polygon_px = np.array([
            [int(pt[0] * fw), int(pt[1] * fh)] for pt in roi_pts_norm
        ], dtype=np.int32)

        stop_line_coord = compute_stop_line(roi_polygon_px, q_axis)

        # Run YOLOv8 Tracking with MPS/CPU
        try:
            results = yolo_model.track(
                frame,
                persist=True,
                tracker="bytetrack.yaml",
                conf=conf_thresh,
                device=DEVICE,
                verbose=False
            )
        except Exception as e:
            # Fallback to plain detect if tracking fails
            results = yolo_model(frame, conf=conf_thresh, device=DEVICE, verbose=False)

        # Parse detections
        tracked_vehicles = []
        dwelling_vehicles = []
        class_counts = {"car": 0, "motorcycle": 0, "bus": 0, "truck": 0}
        
        # Copies for drawing
        clean_frame = frame.copy()
        hud_frame = frame.copy()

        if results and len(results) > 0 and results[0].boxes is not None:
            boxes_obj = results[0].boxes
            has_id = boxes_obj.id is not None
            
            for i, box in enumerate(boxes_obj):
                cls_id = int(box.cls[0].item())
                raw_name = yolo_model.names.get(cls_id, str(cls_id)).lower()
                
                # Normalize name
                canonical_class = None
                if "motor" in raw_name or "bike" in raw_name:
                    canonical_class = "motorcycle"
                elif "car" in raw_name:
                    canonical_class = "car"
                elif "bus" in raw_name:
                    canonical_class = "bus"
                elif "truck" in raw_name:
                    canonical_class = "truck"
                
                if canonical_class is None:
                    continue

                class_counts[canonical_class] += 1
                conf = float(box.conf[0].item())
                x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                track_id = int(boxes_obj.id[i].item()) if has_id else (1000 + i)

                # Grounding point (bottom-center)
                cx = int((x1 + x2) / 2)
                cy = int(y2)
                
                # Check point in ROI
                in_roi = False
                if len(roi_polygon_px) >= 3:
                    contour = roi_polygon_px.reshape((-1, 1, 2)).astype(np.float32)
                    in_roi = cv2.pointPolygonTest(contour, (float(cx), float(cy)), False) >= 0

                # Track position history & calculate velocity
                history = state.track_history[track_id]
                history.append((cx, cy))
                
                speed_px = 0.0
                if len(history) >= 2:
                    dx = history[-1][0] - history[-2][0]
                    dy = history[-1][1] - history[-2][1]
                    speed_px = math.sqrt(dx * dx + dy * dy)

                # Dwell counter
                if in_roi and speed_px < state.dwelling_speed_thresh:
                    state.track_dwell_counter[track_id] += 1
                else:
                    state.track_dwell_counter[track_id] = max(0, state.track_dwell_counter[track_id] - 1)

                is_dwelling = state.track_dwell_counter[track_id] >= state.dwelling_frames_thresh

                v_info = {
                    "id": track_id,
                    "class": canonical_class,
                    "conf": round(conf, 2),
                    "box": (x1, y1, x2, y2),
                    "bottom_center": (cx, cy),
                    "center": (int((x1 + x2) / 2), int((y1 + y2) / 2)),
                    "speed_px": round(speed_px, 1),
                    "dwelling_frames": state.track_dwell_counter[track_id],
                    "is_dwelling": is_dwelling,
                    "in_roi": in_roi
                }
                tracked_vehicles.append(v_info)
                if in_roi and is_dwelling:
                    dwelling_vehicles.append(v_info)

        # Calculate Module 2 Metrics
        occupancy_pct, combined_mask = calculate_morphological_occupancy(
            frame.shape, dwelling_vehicles, roi_polygon_px, kernel_sz
        )
        queue_len_m = calculate_queue_length(
            dwelling_vehicles, stop_line_coord, q_axis, p2m, body_len
        )
        pressure = round(occupancy_pct * queue_len_m, 1)

        if pressure < 120:
            traffic_level = "NORMAL"
        elif pressure < 350:
            traffic_level = "MODERATE"
        else:
            traffic_level = "CONGESTED"

        # -------------------------------------------------------------------
        # Render Overlays
        # -------------------------------------------------------------------
        # Clean Frame (Digital Twin Module 1)
        for v in tracked_vehicles:
            tid = v["id"]
            x1, y1, x2, y2 = v["box"]
            cls_name = v["class"]
            
            # Draw trajectory trail
            pts = list(state.track_history[tid])
            for k in range(1, len(pts)):
                alpha = k / len(pts)
                color = (int(0 * alpha), int(200 * alpha), int(255 * alpha))
                cv2.line(clean_frame, pts[k - 1], pts[k], color, 2)

            # Box and ID
            box_col = (0, 204, 255) if v["in_roi"] else (230, 230, 230)
            cv2.rectangle(clean_frame, (x1, y1), (x2, y2), box_col, 2)
            cv2.circle(clean_frame, v["bottom_center"], 4, (0, 0, 255), -1)
            
            lbl = f"#{tid} {cls_name}"
            cv2.putText(clean_frame, lbl, (x1, max(15, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
            cv2.putText(clean_frame, lbl, (x1, max(15, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

        # HUD Frame (Module 2 & Combined View)
        # 1. Semi-transparent ROI polygon
        if len(roi_polygon_px) >= 3:
            overlay = hud_frame.copy()
            cv2.fillPoly(overlay, [roi_polygon_px], (255, 220, 100))  # light blue-yellow
            cv2.addWeighted(overlay, 0.25, hud_frame, 0.75, 0, hud_frame)
            cv2.polylines(hud_frame, [roi_polygon_px], isClosed=True, color=(255, 120, 0), thickness=2)

        # 2. Stop Line
        if stop_line_coord > 0:
            if q_axis == "y":
                cv2.line(hud_frame, (0, stop_line_coord), (fw, stop_line_coord), (0, 0, 255), 2)
                cv2.putText(hud_frame, "STOP LINE", (15, stop_line_coord - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
            else:
                cv2.line(hud_frame, (stop_line_coord, 0), (stop_line_coord, fh), (0, 0, 255), 2)
                cv2.putText(hud_frame, "STOP LINE", (stop_line_coord + 8, 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

        # 3. Vehicle bounding boxes on HUD
        for v in tracked_vehicles:
            x1, y1, x2, y2 = v["box"]
            tid = v["id"]
            if v["in_roi"]:
                if v["is_dwelling"]:
                    color = (0, 0, 255)      # Red = Queued in ROI
                    status_text = "QUEUED"
                else:
                    color = (0, 165, 255)    # Orange = Moving inside ROI
                    status_text = "ROI"
            else:
                color = (180, 180, 180)      # Gray = Outside ROI
                status_text = "OUT"

            cv2.rectangle(hud_frame, (x1, y1), (x2, y2), color, 2)
            cv2.circle(hud_frame, v["bottom_center"], 4, color, -1)
            
            info_tag = f"#{tid} {v['class']} [{status_text}]"
            cv2.putText(hud_frame, info_tag, (x1, max(15, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 2)

        # 4. Morphological Mask BGR representation
        mask_bgr = cv2.cvtColor(combined_mask, cv2.COLOR_GRAY2BGR)
        # Highlight occupied area in green on mask
        mask_bgr[:, :, 0] = 0
        mask_bgr[:, :, 2] = 0
        # Draw ROI border on mask for visual context
        if len(roi_polygon_px) >= 3:
            cv2.polylines(mask_bgr, [roi_polygon_px], isClosed=True, color=(100, 100, 255), thickness=1)

        # Encode JPEG streams
        _, enc_hud = cv2.imencode('.jpg', hud_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        _, enc_clean = cv2.imencode('.jpg', clean_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        _, enc_mask = cv2.imencode('.jpg', mask_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])

        # FPS calculation
        frame_count += 1
        now = time.time()
        elapsed = now - last_fps_time
        calc_fps = state.fps
        if elapsed >= 0.5:
            calc_fps = round(frame_count / elapsed, 1)
            frame_count = 0
            last_fps_time = now

        # Update EngineState
        with state.lock:
            state.fps = calc_fps
            state.total_detected = len(tracked_vehicles)
            state.class_counts = class_counts
            state.vehicles_in_roi_count = sum(1 for v in tracked_vehicles if v["in_roi"])
            state.occupancy_pct = round(occupancy_pct, 1)
            state.queue_length_m = queue_len_m
            state.pressure_score = pressure
            state.traffic_level = traffic_level
            state.tracked_vehicles = tracked_vehicles
            state.recent_history.append((round(now, 1), pressure))
            
            state.latest_video_jpeg = enc_hud.tobytes()
            state.latest_clean_jpeg = enc_clean.tobytes()
            state.latest_mask_jpeg = enc_mask.tobytes()
            state.latest_raw_frame = hud_frame.copy()

        # Slight pause to yield CPU
        time.sleep(0.01)

    if cap is not None:
        cap.release()
    print("[AI-ENGINE] Video worker thread stopped.")

# ---------------------------------------------------------------------------
# FastAPI Endpoints
# ---------------------------------------------------------------------------
app = FastAPI(title="Digital Twin Traffic AI Engine", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    threading.Thread(target=video_worker, daemon=True).start()

class SourceRequest(BaseModel):
    source_type: str  # 'preset', 'file', 'webcam'
    path: Optional[str] = None
    camera_index: Optional[int] = 0

class ROIRequest(BaseModel):
    points: List[List[float]]  # normalized 0.0 - 1.0 coords [[x, y], ...]
    queue_axis: Optional[str] = "y"

class ConfigRequest(BaseModel):
    conf_threshold: Optional[float] = None
    dilation_kernel: Optional[int] = None
    pixel_to_meter: Optional[float] = None
    queue_axis: Optional[str] = None
    loop_video: Optional[bool] = None
    paused: Optional[bool] = None

@app.get("/api/status")
def get_status():
    with state.lock:
        return {
            "status": "RUNNING",
            "device": DEVICE,
            "source_type": state.source_type,
            "source_path": state.source_path,
            "camera_index": state.camera_index,
            "paused": state.paused,
            "fps": state.fps,
            "conf_threshold": state.conf_threshold,
            "roi_points": state.roi_points_norm,
            "queue_axis": state.queue_axis
        }

@app.post("/api/source")
def set_source(req: SourceRequest):
    with state.lock:
        if req.source_type == "preset":
            state.source_type = "preset"
            state.source_path = os.path.join(BASE_DIR, "intersection_1_roi.mp4")
            state.roi_points_norm = [
                [0.44, 0.84], [0.61, 0.42], [0.22, 0.38], [0.00, 0.50], [0.00, 0.79]
            ]
        elif req.source_type == "file":
            if not req.path or not os.path.exists(req.path):
                raise HTTPException(status_code=400, detail=f"File not found: {req.path}")
            state.source_type = "file"
            state.source_path = req.path
        elif req.source_type == "webcam":
            state.source_type = "webcam"
            state.camera_index = req.camera_index if req.camera_index is not None else 0
            # Default central ROI for webcam
            state.roi_points_norm = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]
        else:
            raise HTTPException(status_code=400, detail="Invalid source_type")
        
        # Reset state trackers
        state.track_history.clear()
        state.track_dwell_counter.clear()

    return {"status": "SUCCESS", "source_type": state.source_type}

@app.post("/api/roi")
def set_roi(req: ROIRequest):
    if len(req.points) < 3:
        raise HTTPException(status_code=400, detail="At least 3 points required for polygon ROI")
    with state.lock:
        state.roi_points_norm = req.points
        if req.queue_axis in ["y", "x"]:
            state.queue_axis = req.queue_axis
    return {"status": "SUCCESS", "points_count": len(req.points)}

@app.post("/api/config")
def update_config(req: ConfigRequest):
    with state.lock:
        if req.conf_threshold is not None:
            state.conf_threshold = max(0.1, min(0.95, req.conf_threshold))
        if req.dilation_kernel is not None:
            state.dilation_kernel = max(3, req.dilation_kernel)
        if req.pixel_to_meter is not None:
            state.pixel_to_meter = req.pixel_to_meter
        if req.queue_axis in ["y", "x"]:
            state.queue_axis = req.queue_axis
        if req.loop_video is not None:
            state.loop_video = req.loop_video
        if req.paused is not None:
            state.paused = req.paused
    return {"status": "SUCCESS"}

@app.get("/api/telemetry")
def get_telemetry():
    with state.lock:
        # Simplify tracked vehicles list for JSON payload
        vehicles = []
        for v in state.tracked_vehicles:
            vehicles.append({
                "id": v["id"],
                "class": v["class"],
                "conf": v["conf"],
                "box": v["box"],
                "center": v["center"],
                "bottom_center": v["bottom_center"],
                "speed_px": v["speed_px"],
                "dwelling_frames": v["dwelling_frames"],
                "is_dwelling": v["is_dwelling"],
                "in_roi": v["in_roi"]
            })

        return {
            "timestamp": round(time.time(), 2),
            "fps": state.fps,
            "total_detected": state.total_detected,
            "class_counts": state.class_counts,
            "vehicles_in_roi_count": state.vehicles_in_roi_count,
            "occupancy_pct": state.occupancy_pct,
            "queue_length_m": state.queue_length_m,
            "pressure_score": state.pressure_score,
            "traffic_level": state.traffic_level,
            "tracked_vehicles": vehicles,
            "history": list(state.recent_history)
        }

def mjpeg_generator(stream_type: str):
    while state.running:
        frame_bytes = None
        with state.lock:
            if stream_type == "video":
                frame_bytes = state.latest_video_jpeg
            elif stream_type == "clean":
                frame_bytes = state.latest_clean_jpeg
            elif stream_type == "mask":
                frame_bytes = state.latest_mask_jpeg

        if frame_bytes is not None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(0.033)  # ~30 fps max streaming rate

@app.get("/api/stream/video")
def stream_video():
    return StreamingResponse(
        mjpeg_generator("video"),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.get("/api/stream/clean")
def stream_clean():
    return StreamingResponse(
        mjpeg_generator("clean"),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.get("/api/stream/mask")
def stream_mask():
    return StreamingResponse(
        mjpeg_generator("mask"),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.post("/api/snapshot")
def save_snapshot():
    with state.lock:
        if state.latest_raw_frame is None:
            raise HTTPException(status_code=400, detail="No frame available")
        frame = state.latest_raw_frame.copy()
        metrics = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "occupancy_pct": state.occupancy_pct,
            "queue_length_m": state.queue_length_m,
            "pressure_score": state.pressure_score,
            "traffic_level": state.traffic_level,
            "total_vehicles": state.total_detected
        }

    snapshots_dir = os.path.join(BASE_DIR, "snapshots")
    os.makedirs(snapshots_dir, exist_ok=True)
    filename = f"snapshot_{int(time.time())}.jpg"
    filepath = os.path.join(snapshots_dir, filename)
    cv2.imwrite(filepath, frame)

    return {"status": "SUCCESS", "filepath": filepath, "metrics": metrics}

if __name__ == "__main__":
    import uvicorn
    port = 8000
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    print(f"[AI-ENGINE] Starting server on http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
