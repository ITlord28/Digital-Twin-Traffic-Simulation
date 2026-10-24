"""
Digital Twin — Adaptive Traffic Signal Control (Max-Pressure)
Computer Vision Pipeline using YOLOv8

Architecture:
  - 4 video inputs (1 per direction: North, South, East, West)
  - YOLOv8 Detect + Track → bottom-edge point filtering via ROI polygon
  - Morphological occupancy (binary mask + dilation)
  - Queue length in meters (stop line → farthest vehicle)
  - Pressure = Occupancy × Queue_Length
  - JSON output every ~1s for GAMA Platform consumption

Frame separation:
  - clean_frame: original video + YOLO bboxes only (for Digital Twin display)
  - debug_frame: ROI polygon + stop line + morphological mask (dev/debug only)
"""

import json
import os
import time
import tempfile
import threading

import cv2
import numpy as np
import torch
from ultralytics import YOLO

# Auto-detect Apple Silicon GPU (MPS) or default to CPU
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = "yolov8s.pt"
# Use absolute path so GAMA can reference the exact same file
JSON_OUTPUT = os.path.join(BASE_DIR, "traffic_data.json")

DETECTION_INTERVAL = 0.3          # seconds between detections (0.2–0.5)
CONFIDENCE_THRESHOLD = 0.4        # minimum detection confidence
LOOP_VIDEO = True                 # True = lặp lại video khi hết
TRACK_MEMORY_FRAMES = 15          # frames to keep a vehicle in ROI memory

# --- Chế độ Debug ---
DEBUG_MODE = False               # True = hiện debug_frame, False = chỉ hiện clean_frame

# --- Pixel-to-Meter conversion ---
# Mặc định: 20 pixel ≈ 1 mét. Calibrate lại bằng SUMO khi hệ thống chạy ổn.
PIXEL_TO_METER = 0.05

# --- Vehicle body length estimate (meters) ---
# Cộng thêm vào queue length vì bottom-edge chỉ là mép lốp sau,
# cần tính cả thân xe cuối cùng trong hàng đợi.
VEHICLE_BODY_LENGTH_M = 4.5

# --- Morphological dilation kernel ---
MORPH_KERNEL_SIZE = 15            # kích thước kernel dilation (gộp xe gần nhau)

# --- Queue detection ---
QUEUE_DWELLING_FRAMES = 10       # frames xe phải dừng trong ROI để tính là "đang chờ"

# ---------------------------------------------------------------------------
# GPS coordinates of the main intersection (shared for all directions)
# ---------------------------------------------------------------------------
INTERSECTION_LAT = 10.0280000
INTERSECTION_LON = 105.7490000

# ---------------------------------------------------------------------------
# DIRECTION_CONFIGS — 4 Directions, 2 videos each
#
# Mỗi hướng có:
#   - video_vehicles: video để chạy YOLO đếm tổng số xe (vehicle_count)
#   - video_roi: video để chạy YOLO + ROI tính Occupancy, Queue_Length, Pressure
#   - roi_points: tọa độ đa giác ROI (tỉ lệ % frame width/height)
#   - stop_line: TỰ SUY LUẬN từ roi_points
#     (stop_line_y = max Y trong roi_points cho hướng dọc N/S,
#      stop_line_x = max X trong roi_points cho hướng ngang E/W)
#   - queue_axis: "y" cho hướng dọc (N/S), "x" cho hướng ngang (E/W)
#
# >>> Thay đường dẫn video và tọa độ ROI cho đúng hệ thống của bạn <<<
# ---------------------------------------------------------------------------

DIRECTION_CONFIGS = {
    "north": {
        "video_vehicles": os.path.join(BASE_DIR, "intersection_1_vehicles.mp4"),
        "video_roi": os.path.join(BASE_DIR, "intersection_1_roi.mp4"),
        "label": "NORTH",
        "roi_points": [
            (0.44, 0.84),   # point 1 — [390, 414]
            (0.61, 0.42),   # point 2 — [544, 205]
            (0.22, 0.38),   # point 3 — [199, 187]
            (0.00, 0.50),   # point 4 — [3, 245]
            (0.00, 0.79),   # point 5 — [3, 388]
        ],
        "queue_axis": "y",  # xe xếp hàng theo trục Y (dọc)
    },
    "south": {
        "video_vehicles": os.path.join(BASE_DIR, "intersection_2_vehicles.mp4"),
        "video_roi": os.path.join(BASE_DIR, "intersection_2_roi.mp4"),
        "label": "SOUTH",
        "roi_points": [
            (0.44, 0.84),
            (0.61, 0.42),
            (0.22, 0.38),
            (0.00, 0.50),
            (0.00, 0.79),
        ],
        "queue_axis": "y",
    },
    "east": {
        "video_vehicles": os.path.join(BASE_DIR, "intersection_3_vehicles.mp4"),
        "video_roi": os.path.join(BASE_DIR, "intersection_3_roi .mp4"),
        "label": "EAST",
        "roi_points": [
            (0.44, 0.84),
            (0.61, 0.42),
            (0.22, 0.38),
            (0.00, 0.50),
            (0.00, 0.79),
        ],
        "queue_axis": "x",  # xe xếp hàng theo trục X (ngang)
    },
    "west": {
        "video_vehicles": os.path.join(BASE_DIR, "intersection_4_vehicles.mp4"),
        "video_roi": os.path.join(BASE_DIR, "intersection_4_roi  .mp4"),
        "label": "WEST",
        "roi_points": [
            (0.44, 0.84),
            (0.61, 0.42),
            (0.22, 0.38),
            (0.00, 0.50),
            (0.00, 0.79),
        ],
        "queue_axis": "x",
    },
}

# YOLO class IDs for vehicles (Custom model trained on Vehicle Vietnam-CanTho dataset)
# Class order: 0=bus, 1=car, 2=motorbike, 3=truck
# NOTE: If switching back to a COCO model (yolov8s.pt etc.),
#       use: {2: "car", 3: "motorbike", 5: "bus", 7: "truck"}
VEHICLE_CLASSES = {
    5: "bus",
    2: "car",
    3: "motorbike",
    7: "truck",
}

# Colors for bounding box overlay (BGR)
OVERLAY_COLORS = {
    "car":       (0, 255, 100),
    "motorbike": (0, 200, 255),
    "bus":       (255, 150, 0),
    "truck":     (100, 100, 255),
}


# ---------------------------------------------------------------------------
# ROI Helper Functions
# ---------------------------------------------------------------------------

def build_roi_polygon(roi_points_frac, frame_width, frame_height):
    """Convert fractional ROI points to pixel coordinates.

    Args:
        roi_points_frac: list of (frac_x, frac_y) tuples (0.0–1.0)
        frame_width: pixel width of video frame
        frame_height: pixel height of video frame

    Returns:
        np.ndarray of shape (N, 2) with int32 pixel coordinates
    """
    pts = [(int(frame_width * fx), int(frame_height * fy))
           for fx, fy in roi_points_frac]
    return np.array(pts, dtype=np.int32)


def compute_stop_line(roi_polygon_px, queue_axis):
    """Auto-derive stop line coordinate from ROI polygon.

    For vertical queues (N/S): stop_line = max Y in ROI (bottom edge of ROI)
    For horizontal queues (E/W): stop_line = max X in ROI (right edge of ROI)

    Args:
        roi_polygon_px: np.ndarray shape (N, 2) — pixel coordinates
        queue_axis: "y" or "x"

    Returns:
        int — pixel coordinate of the stop line
    """
    if queue_axis == "y":
        return int(np.max(roi_polygon_px[:, 1]))
    else:
        return int(np.max(roi_polygon_px[:, 0]))


# ---------------------------------------------------------------------------
# Vehicle detection helpers
# ---------------------------------------------------------------------------

def get_vehicle_bottom_center(box):
    """Lấy điểm giữa mép dưới Bbox (vị trí lốp xe chạm đường).

    Thay vì tâm bbox, dùng (x_center, y_max) để kiểm tra
    lốp xe có nằm trong ROI không — chính xác hơn cho camera nghiêng.
    """
    x1, y1, x2, y2 = box.xyxy[0]
    cx = int((x1 + x2) / 2)
    cy = int(y2)  # Mép dưới = y_max
    return (cx, cy)


def is_point_in_roi(point, roi_contour):
    """Check if a point is inside the ROI polygon using OpenCV native function.

    Uses cv2.pointPolygonTest which is faster than manual ray casting.

    Args:
        point: tuple (x, y)
        roi_contour: np.ndarray shape (N, 2) — ROI polygon pixel coords

    Returns:
        True if point is inside or on the edge of the polygon
    """
    # cv2.pointPolygonTest requires float32 contour with shape (N, 1, 2)
    contour = roi_contour.reshape((-1, 1, 2)).astype(np.float32)
    result = cv2.pointPolygonTest(contour, (float(point[0]), float(point[1])), False)
    return result >= 0  # >= 0 means inside or on edge


def detect_vehicles(model, frame):
    """Run YOLO tracking on a single frame and return results.

    Uses tracking instead of just detection to maintain vehicle IDs across frames.
    """
    results = model.track(
        frame, conf=CONFIDENCE_THRESHOLD, persist=True, verbose=False, device=DEVICE
    )
    return results


# ---------------------------------------------------------------------------
# Morphological Occupancy (Component 4)
# ---------------------------------------------------------------------------

def calculate_morphological_occupancy(frame_shape, vehicles_in_roi, roi_polygon_px,
                                       kernel_size=MORPH_KERNEL_SIZE):
    """Tính Occupancy bằng morphological mask.

    Algorithm:
      1. Tạo mask đen (zeros) cùng kích thước frame
      2. Vẽ filled rectangles (bbox) của xe trong ROI lên mask (trắng)
      3. Áp dụng Dilation để gộp các xe đứng gần nhau
      4. Tạo ROI mask riêng biệt
      5. AND hai mask → chỉ giữ phần xe trong ROI
      6. Occupancy = (pixel trắng trong AND) / (pixel trắng trong ROI mask) × 100

    Args:
        frame_shape: (h, w, c) — shape of the video frame
        vehicles_in_roi: list of dicts with 'box' key (x1, y1, x2, y2)
        roi_polygon_px: np.ndarray shape (N, 2) — ROI pixel coordinates
        kernel_size: dilation kernel size

    Returns:
        (occupancy_pct, combined_mask):
          - occupancy_pct: float 0–100
          - combined_mask: np.ndarray (h, w) uint8 — for debug display
    """
    h, w = frame_shape[:2]

    # 1. Mask xe (vẽ bbox đầy lên mask đen)
    vehicle_mask = np.zeros((h, w), dtype=np.uint8)
    for v in vehicles_in_roi:
        x1, y1, x2, y2 = v["box"]
        cv2.rectangle(vehicle_mask, (x1, y1), (x2, y2), 255, -1)

    # 2. Dilation — gộp các xe đứng gần nhau thành khối liên tục
    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (kernel_size, kernel_size)
    )
    vehicle_mask = cv2.dilate(vehicle_mask, kernel, iterations=1)

    # 3. ROI mask
    roi_mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillPoly(roi_mask, [roi_polygon_px], 255)

    # 4. AND — chỉ giữ phần xe nằm trong ROI
    combined = cv2.bitwise_and(vehicle_mask, roi_mask)

    # 5. Tỉ lệ pixel
    roi_pixels = cv2.countNonZero(roi_mask)
    occupied_pixels = cv2.countNonZero(combined)

    occupancy = (occupied_pixels / roi_pixels * 100.0) if roi_pixels > 0 else 0.0
    return min(occupancy, 100.0), combined


# ---------------------------------------------------------------------------
# Queue Length in Meters (Component 5)
# ---------------------------------------------------------------------------

def calculate_queue_length(vehicles_in_roi, stop_line_coord, queue_axis,
                           pixel_to_meter=PIXEL_TO_METER,
                           body_length=VEHICLE_BODY_LENGTH_M):
    """Tính chiều dài hàng đợi (Queue Length) bằng mét.

    Tính khoảng cách từ vạch dừng (stop line) đến xe xa nhất trong ROI,
    cộng thêm chiều dài thân xe (~4.5m) vì bottom-edge chỉ là mép lốp sau.

    Args:
        vehicles_in_roi: list of dicts with 'bottom_center' key (x, y)
        stop_line_coord: int — pixel Y (for queue_axis="y") or pixel X (for "x")
        queue_axis: "y" or "x" — trục xếp hàng
        pixel_to_meter: conversion factor
        body_length: estimated vehicle body length to add (meters)

    Returns:
        queue_length_meters: float
    """
    if len(vehicles_in_roi) == 0:
        return 0.0

    # Lấy tọa độ theo trục xếp hàng
    if queue_axis == "y":
        positions = [v["bottom_center"][1] for v in vehicles_in_roi]
    else:
        positions = [v["bottom_center"][0] for v in vehicles_in_roi]

    # Khoảng cách xa nhất so với vạch dừng
    max_distance_pixels = max(abs(pos - stop_line_coord) for pos in positions)

    # Quy đổi sang mét + thêm chiều dài thân xe
    length_meters = (max_distance_pixels * pixel_to_meter) + body_length

    return round(length_meters, 2)


# ---------------------------------------------------------------------------
# Drawing helpers (debug_frame only)
# ---------------------------------------------------------------------------

def draw_roi_debug(frame, roi_polygon_px, label, color=(0, 255, 0)):
    """Vẽ đa giác ROI lên debug_frame."""
    pts = roi_polygon_px.reshape((-1, 1, 2))
    cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=2)

    # Semi-transparent fill
    overlay = frame.copy()
    cv2.fillPoly(overlay, [roi_polygon_px], color)
    cv2.addWeighted(overlay, 0.15, frame, 0.85, 0, frame)

    # Label
    label_pt = (int(roi_polygon_px[0][0]) + 10, int(roi_polygon_px[0][1]) + 25)
    cv2.putText(frame, label, label_pt,
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    return frame


def draw_stop_line_debug(frame, stop_line_coord, queue_axis, color=(0, 0, 255)):
    """Vẽ vạch dừng lên debug_frame."""
    h, w = frame.shape[:2]
    if queue_axis == "y":
        cv2.line(frame, (0, stop_line_coord), (w, stop_line_coord), color, 2)
        cv2.putText(frame, "STOP LINE", (10, stop_line_coord - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    else:
        cv2.line(frame, (stop_line_coord, 0), (stop_line_coord, h), color, 2)
        cv2.putText(frame, "STOP", (stop_line_coord + 5, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    return frame


def draw_mask_overlay_debug(frame, mask, color=(0, 255, 255)):
    """Vẽ morphological mask lên debug_frame dưới dạng overlay màu."""
    colored_mask = np.zeros_like(frame)
    colored_mask[mask > 0] = color
    cv2.addWeighted(colored_mask, 0.4, frame, 1.0, 0, frame)
    return frame


def draw_bottom_points_debug(frame, vehicles_in_roi, color=(255, 0, 255)):
    """Vẽ điểm bottom-center của các xe trong ROI lên debug_frame."""
    for v in vehicles_in_roi:
        pt = v["bottom_center"]
        cv2.circle(frame, pt, 5, color, -1)
        cv2.circle(frame, pt, 7, color, 2)
    return frame


def draw_metrics_overlay(frame, metrics, label=""):
    """Draw metrics panel on frame (used for both clean_frame and debug_frame)."""
    h, w = frame.shape[:2]

    # Semi-transparent background box
    overlay = frame.copy()
    box_w = 300
    box_h = 105
    x1, y1 = 10, 10
    x2, y2 = x1 + box_w, y1 + box_h
    cv2.rectangle(overlay, (x1, y1), (x2, y2), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 200), 1)

    # Title
    title = f"Digital Twin: {label}" if label else "Digital Twin"
    cv2.putText(frame, title, (x1 + 10, y1 + 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    # Metrics
    y = y1 + 55
    items = [
        (f"Occupancy: {metrics.get('occupancy', 0):.1f}%", (0, 255, 100)),
    ]
    for text, color in items:
        cv2.putText(frame, text, (x1 + 15, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        y += 28

    return frame


# ---------------------------------------------------------------------------
# Tracking Manager — lọc xe dừng chờ (v ≈ 0)
# ---------------------------------------------------------------------------

class TrackingManager:
    """Manages vehicle tracking across frames for queue detection and persistent memory.

    Chỉ xe dừng đủ lâu (>= dwelling_threshold frames) trong ROI mới được
    tính vào occupancy và queue length.
    """

    def __init__(self, dwelling_threshold=QUEUE_DWELLING_FRAMES):
        self.roi_memory = {}
        # {track_id: {
        #     'class': str,
        #     'box': (x1, y1, x2, y2),
        #     'bottom_center': (cx, cy),
        #     'in_roi': bool,
        #     'frames_missing': 0,
        #     'frames_in_roi': 1,
        # }}
        self.dwelling_threshold = dwelling_threshold

    def update(self, vehicle_tracks):
        """Update tracking information with current frame's detections.

        Args:
            vehicle_tracks: dict mapping track_id to vehicle info dict
        """
        current_ids = set(vehicle_tracks.keys())

        # 1. Update existing tracked vehicles
        for track_id in list(self.roi_memory.keys()):
            if track_id in current_ids:
                curr_in_roi = vehicle_tracks[track_id]["in_roi"]
                if curr_in_roi:
                    # Still in ROI: update info and reset missing counter
                    self.roi_memory[track_id]["box"] = vehicle_tracks[track_id]["box"]
                    self.roi_memory[track_id]["bottom_center"] = vehicle_tracks[track_id]["bottom_center"]
                    self.roi_memory[track_id]["frames_missing"] = 0
                    self.roi_memory[track_id]["frames_in_roi"] += 1
                else:
                    # Vehicle has left ROI — remove immediately
                    del self.roi_memory[track_id]
            else:
                # Vehicle not detected this frame — increment missing counter
                self.roi_memory[track_id]["frames_missing"] += 1
                self.roi_memory[track_id]["frames_in_roi"] += 1

                if self.roi_memory[track_id]["frames_missing"] > TRACK_MEMORY_FRAMES:
                    del self.roi_memory[track_id]

        # 2. Add new detections that are in ROI
        for track_id, info in vehicle_tracks.items():
            if info["in_roi"] and track_id not in self.roi_memory:
                self.roi_memory[track_id] = {
                    "class": info["class"],
                    "box": info["box"],
                    "bottom_center": info["bottom_center"],
                    "in_roi": True,
                    "frames_missing": 0,
                    "frames_in_roi": 1,
                }

    def get_dwelling_vehicles(self):
        """Get list of vehicles that have been dwelling in ROI long enough (v ≈ 0).

        Returns:
            list of dicts with 'box', 'bottom_center', 'class' keys
        """
        dwelling = []
        for track_id, info in self.roi_memory.items():
            if info["frames_in_roi"] >= self.dwelling_threshold:
                dwelling.append({
                    "box": info["box"],
                    "bottom_center": info["bottom_center"],
                    "class": info["class"],
                })
        return dwelling

    def get_all_roi_vehicles(self):
        """Get ALL vehicles currently tracked in ROI (including not yet dwelling).

        Returns:
            list of dicts with 'box', 'bottom_center', 'class' keys
        """
        return [
            {
                "box": info["box"],
                "bottom_center": info["bottom_center"],
                "class": info["class"],
            }
            for info in self.roi_memory.values()
        ]


# ---------------------------------------------------------------------------
# JSON Output (atomic write)
# ---------------------------------------------------------------------------

def write_json(data, filepath=JSON_OUTPUT):
    """Safely write data to JSON using atomic write (write to temp → rename).

    This prevents file corruption if GAMA reads mid-write.

    Steps:
      1. Write JSON to a temp file in the same directory
      2. fsync to ensure data is flushed to disk
      3. Atomically rename temp → target (POSIX guarantees this)
    """
    dir_name = os.path.dirname(os.path.abspath(filepath))

    fd, tmp_path = tempfile.mkstemp(suffix=".tmp", dir=dir_name)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, filepath)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


# ---------------------------------------------------------------------------
# Per-direction processing thread (Dual-video: vehicles + ROI)
# ---------------------------------------------------------------------------

class DirectionProcessor(threading.Thread):
    """Thread that processes 1 video for a single direction.

    Architecture:
      - YOLO Detect + Track → ROI filtering → Occupancy

    Display: Chỉ hiển thị clean_frame từ video ROI.
    """

    def __init__(self, direction, config, model_path, shared_data, lock):
        """
        Args:
            direction: "north" | "south" | "east" | "west"
            config: dict from DIRECTION_CONFIGS[direction]
            model_path: path to YOLO model weights
            shared_data: shared dict for all directions
            lock: threading lock for shared_data
        """
        super().__init__(daemon=True)
        self.direction = direction
        self.config = config
        self.model_path = model_path
        
        self.model_roi = YOLO(model_path)
        self.shared_data = shared_data
        self.lock = lock
        self.running = True

        self.label = config["label"]
        self.queue_axis = config["queue_axis"]

        # Will be initialized on first ROI frame (need frame dimensions)
        self.roi_polygon_px = None
        self.stop_line_coord = None

        self.tracking_manager = TrackingManager()
        self.latest_metrics = {
            "occupancy": 0.0,
        }

        # Frames for display (main thread reads these)
        self.latest_clean_frame = None
        self.latest_debug_frame = None
        self.frame_lock = threading.Lock()

    def _init_roi(self, frame_width, frame_height):
        """Initialize ROI polygon and stop line from config (called once)."""
        self.roi_polygon_px = build_roi_polygon(
            self.config["roi_points"], frame_width, frame_height
        )
        self.stop_line_coord = compute_stop_line(
            self.roi_polygon_px, self.queue_axis
        )
        print(f"[INFO] [{self.label}] ROI initialized: {self.roi_polygon_px.tolist()}")
        print(f"[INFO] [{self.label}] Stop line ({self.queue_axis}): {self.stop_line_coord}px")

    def _process_roi_detections(self, results, frame_shape):
        """Process YOLO results from ROI video: filter by ROI, compute metrics.

        Args:
            results: YOLO tracking results
            frame_shape: (h, w, c)

        Returns:
            (roi_metrics, dwelling_vehicles, morph_mask)
            roi_metrics contains: occupancy, queue_length, pressure
            (vehicle_count sẽ được gộp từ video vehicles riêng)
        """
        vehicle_tracks = {}

        for result in results:
            if result.boxes is None or result.boxes.id is None:
                continue

            for box, track_id in zip(result.boxes, result.boxes.id):
                track_id = int(track_id)
                cls_id = int(box.cls[0])

                if cls_id not in VEHICLE_CLASSES:
                    continue

                vehicle_class = VEHICLE_CLASSES[cls_id]
                bottom_center = get_vehicle_bottom_center(box)
                in_roi = is_point_in_roi(bottom_center, self.roi_polygon_px)

                x1, y1, x2, y2 = box.xyxy[0]
                vehicle_tracks[track_id] = {
                    "class": vehicle_class,
                    "bottom_center": bottom_center,
                    "box": (int(x1), int(y1), int(x2), int(y2)),
                    "in_roi": in_roi,
                    "conf": float(box.conf[0]),
                }

        # Update tracking manager (persistent memory, filters by dwelling time)
        self.tracking_manager.update(vehicle_tracks)

        # Get vehicles that are dwelling in ROI (v ≈ 0)
        dwelling_vehicles = self.tracking_manager.get_dwelling_vehicles()

        # --- Morphological Occupancy ---
        occupancy, morph_mask = calculate_morphological_occupancy(
            frame_shape, dwelling_vehicles, self.roi_polygon_px
        )

        roi_metrics = {
            "occupancy": round(occupancy, 1),
        }

        return roi_metrics, dwelling_vehicles, morph_mask

    def _downscale(self, frame, max_width=640):
        """Downscale frame if wider than max_width to save CPU/GPU."""
        h, w = frame.shape[:2]
        if w > max_width:
            scale = max_width / w
            frame = cv2.resize(frame, (max_width, int(h * scale)))
        return frame

    def run(self):
        video_vehicles_path = self.config["video_vehicles"]
        video_roi_path = self.config["video_roi"]

        # --- Check video files exist ---
        vehicles_ok = os.path.exists(video_vehicles_path)
        roi_ok = os.path.exists(video_roi_path)

        if not roi_ok:
            print(f"[WARNING] [{self.label}] ROI video NOT found: {video_roi_path}")
            with self.lock:
                self.shared_data[self.direction] = {
                    "occupancy": 0,
                }
            return

        # --- Open video captures ---
        cap_roi = cv2.VideoCapture(video_roi_path) if roi_ok else None

        if cap_roi and not cap_roi.isOpened():
            print(f"[ERROR] [{self.label}] Cannot open ROI video: {video_roi_path}")
            cap_roi = None

        # Log video info
        total_r = 0
        if cap_roi:
            w_r = int(cap_roi.get(cv2.CAP_PROP_FRAME_WIDTH))
            h_r = int(cap_roi.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps_r = cap_roi.get(cv2.CAP_PROP_FPS)
            total_r = int(cap_roi.get(cv2.CAP_PROP_FRAME_COUNT))
            print(f"[INFO] [{self.label}] ROI video: {w_r}x{h_r}, {fps_r:.1f} FPS, {total_r} frames")

        last_detection_time = 0

        try:
            while self.running:
                # ============================================================
                # Đọc frame từ video ROI
                # ============================================================
                frame_roi = None
                if cap_roi:
                    ret_r, frame_roi = cap_roi.read()
                    if not ret_r:
                        if LOOP_VIDEO:
                            cap_roi.set(cv2.CAP_PROP_POS_FRAMES, 0)
                            _, frame_roi = cap_roi.read()
                        else:
                            frame_roi = None

                    if frame_roi is not None:
                        frame_roi = self._downscale(frame_roi)

                # Nếu video hết (không loop) → dừng
                if frame_roi is None:
                    print(f"[INFO] [{self.label}] Video ended.")
                    break

                # Initialize ROI on first ROI frame
                if frame_roi is not None and self.roi_polygon_px is None:
                    h, w = frame_roi.shape[:2]
                    self._init_roi(w, h)

                now = time.time()

                # === Tạo clean_frame và debug_frame từ video ROI ===
                clean_frame = frame_roi.copy() if frame_roi is not None else None
                debug_frame = frame_roi.copy() if (DEBUG_MODE and frame_roi is not None) else None

                # Only run detection at the configured interval
                if now - last_detection_time >= DETECTION_INTERVAL:

                    # --- VIDEO ROI: occupancy ---
                    roi_metrics = None
                    dwelling_vehicles = []
                    morph_mask = None

                    if frame_roi is not None and self.roi_polygon_px is not None:
                        results_roi = detect_vehicles(self.model_roi, frame_roi)

                        roi_metrics, dwelling_vehicles, morph_mask = self._process_roi_detections(
                            results_roi, frame_roi.shape
                        )

                        # === clean_frame: chỉ YOLO bboxes (từ ROI video) ===
                        if results_roi and len(results_roi) > 0:
                            clean_frame = results_roi[0].plot()

                        # === debug_frame: ROI + stop line + mask + bottom points ===
                        if DEBUG_MODE and debug_frame is not None:
                            if results_roi and len(results_roi) > 0:
                                debug_frame = results_roi[0].plot(img=debug_frame)
                            debug_frame = draw_roi_debug(
                                debug_frame, self.roi_polygon_px,
                                f"ROI_{self.label}", (0, 255, 0)
                            )
                            debug_frame = draw_stop_line_debug(
                                debug_frame, self.stop_line_coord, self.queue_axis
                            )
                            debug_frame = draw_mask_overlay_debug(debug_frame, morph_mask)
                            debug_frame = draw_bottom_points_debug(debug_frame, dwelling_vehicles)

                    # --- Gộp kết quả ---
                    combined_metrics = {
                        "occupancy": roi_metrics["occupancy"] if roi_metrics else 0.0,
                    }
                    self.latest_metrics = combined_metrics

                    # Update shared data (thread-safe)
                    with self.lock:
                        self.shared_data[self.direction] = dict(combined_metrics)

                    # Console output
                    roi_frame_pos = int(cap_roi.get(cv2.CAP_PROP_POS_FRAMES)) if cap_roi else 0
                    roi_total = total_r if cap_roi else 0
                    print(
                        f"[{time.strftime('%H:%M:%S')}] [{self.label}] "
                        f"Frame {roi_frame_pos}/{roi_total} | "
                        f"Occupancy: {combined_metrics['occupancy']}%"
                    )

                    last_detection_time = now

                # --- Vẽ ROI polygon lên clean_frame (luôn hiển thị) ---
                if clean_frame is not None and self.roi_polygon_px is not None:
                    clean_frame = draw_roi_debug(
                        clean_frame, self.roi_polygon_px,
                        f"ROI_{self.label}", (0, 255, 0)
                    )

                # --- Draw metrics overlay (hiển thị trên clean_frame của ROI) ---
                if clean_frame is not None:
                    clean_frame = draw_metrics_overlay(clean_frame, self.latest_metrics, self.label)
                if DEBUG_MODE and debug_frame is not None:
                    debug_frame = draw_metrics_overlay(debug_frame, self.latest_metrics, self.label)

                # --- Resize for display ---
                clean_display = None
                debug_display = None

                if clean_frame is not None:
                    display_h = 480
                    scale_display = display_h / clean_frame.shape[0]
                    display_w = int(clean_frame.shape[1] * scale_display)
                    clean_display = cv2.resize(clean_frame, (display_w, display_h))

                if DEBUG_MODE and debug_frame is not None:
                    display_h = 480
                    scale_display = display_h / debug_frame.shape[0]
                    display_w = int(debug_frame.shape[1] * scale_display)
                    debug_display = cv2.resize(debug_frame, (display_w, display_h))

                with self.frame_lock:
                    self.latest_clean_frame = clean_display
                    self.latest_debug_frame = debug_display

                # Small sleep to prevent CPU spinning
                time.sleep(0.01)

        except Exception as e:
            print(f"[ERROR] [{self.label}] Exception: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if cap_roi:
                cap_roi.release()

    def stop(self):
        self.running = False


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    print("=" * 65)
    print("  Digital Twin — Adaptive Traffic Signal Control (Max-Pressure)")
    print("  Computer Vision Pipeline")
    print("=" * 65)
    print(f"  Device: {DEVICE}")
    print(f"  Model: {MODEL_PATH}")
    print(f"  Debug mode: {'ON' if DEBUG_MODE else 'OFF'}")
    print(f"  Pixel-to-meter: {PIXEL_TO_METER}")
    print(f"  JSON output: {JSON_OUTPUT}")
    print("=" * 65)

    shared_data = {}
    lock = threading.Lock()

    # Initialize shared data with zeros
    for direction in DIRECTION_CONFIGS:
        shared_data[direction] = {
            "occupancy": 0,
        }

    # Start 4 threads — 1 per direction (each thread opens 2 video captures)
    processors = []
    for direction, config in DIRECTION_CONFIGS.items():
        print(f"[INFO] Starting processor for {config['label']} direction")
        print(f"       Vehicles: {config['video_vehicles']}")
        print(f"       ROI:      {config['video_roi']}")
        print(f"       Queue axis: {config['queue_axis']}")

        proc = DirectionProcessor(direction, config, MODEL_PATH, shared_data, lock)
        proc.start()
        processors.append(proc)

    print(f"\n[INFO] {len(processors)} processors started (4 threads)")
    print(f"[INFO] Writing to {JSON_OUTPUT}")
    print("[INFO] Press ESC in any video window to quit.\n")

    # Main loop: aggregate data and write JSON
    try:
        while True:
            # Build JSON payload (Max-Pressure format for GAMA)
            with lock:
                payload = {
                    "timestamp": round(time.time(), 1),
                }
                for direction in DIRECTION_CONFIGS:
                    payload[direction] = dict(shared_data.get(direction, {}))

            write_json(payload)

            # Display windows from the MAIN thread (OpenCV requirement)
            for i, proc in enumerate(processors):
                with proc.frame_lock:
                    clean = proc.latest_clean_frame
                    debug = proc.latest_debug_frame

                if clean is not None:
                    window_title = f"Digital Twin - {proc.label}"
                    cv2.imshow(window_title, clean)
                    # Grid layout: 2 columns
                    col = i % 2
                    row = i // 2
                    cv2.moveWindow(window_title, col * 660, row * 520)

                if DEBUG_MODE and debug is not None:
                    debug_title = f"DEBUG - {proc.label}"
                    cv2.imshow(debug_title, debug)
                    # Debug windows offset to the right
                    col = i % 2
                    row = i // 2
                    cv2.moveWindow(debug_title, col * 660 + 1320, row * 520)

            # Check for ESC key
            key = cv2.waitKey(1) & 0xFF
            if key == 27:
                print("\n[INFO] ESC pressed. Stopping all processors...")
                break

            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user.")
    finally:
        for proc in processors:
            proc.stop()
        for proc in processors:
            proc.join(timeout=3)
        cv2.destroyAllWindows()
        print("[INFO] All processors stopped. Cleanup done.")


if __name__ == "__main__":
    main()
