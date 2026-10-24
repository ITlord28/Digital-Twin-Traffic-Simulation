#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
ĐỀ TÀI NCKH: DIGITAL TWIN - ĐIỀU KHIỂN TÍN HIỆU GIAO THÔNG THÍCH ỨNG
FOLDER 2: TÍNH TOÁN ÁP LỰC GIAO THÔNG VÙNG ROI & ĐỒNG BỘ DIGITAL TWIN
=============================================================================
Mô tả phương pháp khoa học:
  1. Lọc điểm chân xe (Bottom-Edge Grounding): Xác định điểm tiếp xúc lốp xe với mặt đường
     C(x, y) = ((x1 + x2)/2, y2) để triệt tiêu sai lệch do góc nghiêng camera.
  2. Mật độ chiếm dụng hình thái học (Morphological Occupancy %):
     - Vẽ filled bounding box của các xe dừng chờ (dwelling) trong ROI.
     - Dilation (kernel 15x15) để gộp các xe dừng sát nhau thành khối chiếm dụng liên tục.
     - AND bitwise với ROI mask: Đo tỉ lệ % pixel bị chiếm dụng thực tế.
  3. Chiều dài hàng đợi (Queue Length - Mét):
     - Tự động xác định Vạch dừng (Stop Line) từ biên đa giác ROI.
     - Đo khoảng cách từ vạch dừng tới xe xa nhất trong hàng đợi (+ 4.5m thân xe cuối).
  4. Chỉ số Áp lực giao thông thích ứng (Max-Pressure Score):
     Pressure = Occupancy (%) × Queue_Length (m)
  5. Xuất dữ liệu thời gian thực ra file 'roi_telemetry.json' cho mô hình GAMA.

Hướng dẫn sử dụng:
  python calculate_roi_pressure.py
  (Hoặc truyền tham số: python calculate_roi_pressure.py --source 1 hoặc --source 2)
  Phím tắt:
    - 'm': Bật/Tắt chế độ xem Mặt Nạ Hình Thái Học (Morphological Mask)
    - 'p' / Space: Tạm dừng / Tiếp tục
    - 's': Chụp ảnh minh chứng
    - 'q' / ESC: Thoát chương trình
=============================================================================
"""

import os
import sys
import time
import math
import json
import argparse
import tempfile
import collections
import cv2
import numpy as np
import torch
from ultralytics import YOLO

# =============================================================================
# 1. CẤU HÌNH & TỰ ĐỘNG PHÁT HIỆN ĐƯỜNG DẪN
# =============================================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)

DEFAULT_VIDEO = "intersection_1_roi.mp4"
MODEL_PREFERENCE = ["yolov8s.pt", "yolov8n.pt"]
JSON_CONFIG_PATH = os.path.join(CURRENT_DIR, "roi_config.json")
JSON_TELEMETRY_PATHS = [
    os.path.join(CURRENT_DIR, "roi_telemetry.json"),
    os.path.join(CURRENT_DIR, "gama_roi_pressure_trafficsi", "roi_telemetry.json"),
]
JSON_TELEMETRY_PATH = JSON_TELEMETRY_PATHS[0]

# Tọa độ mặc định chuẩn của đề tài (nếu chưa có file roi_config.json)
ROI_POINTS_DEFAULT = [
    (0.44, 0.84),   # Điểm 1: Gần vạch dừng (phải)
    (0.61, 0.42),   # Điểm 2: Xa vạch dừng (phải)
    (0.22, 0.38),   # Điểm 3: Xa vạch dừng (trái)
    (0.00, 0.50),   # Điểm 4: Biên trái trên
    (0.00, 0.79),   # Điểm 5: Biên trái dưới
]

QUEUE_AXIS = "y"                # Trục xếp hàng: "y" (dọc) hoặc "x" (ngang)
PIXEL_TO_METER = 0.05           # 20 pixel ≈ 1 mét
VEHICLE_BODY_LENGTH_M = 4.5     # Chiều dài ước tính thân xe cuối
MORPH_KERNEL_SIZE = 15          # Kernel Dilation gộp cụm xe
DWELLING_FRAMES_THRESH = 8      # Số frame dừng để tính là xếp hàng
CONF_THRESHOLD = 0.35
MAX_FRAME_WIDTH = 960
LOOP_VIDEO = True

def resolve_file(filename):
    """Tìm file ở thư mục hiện tại hoặc thư mục cha."""
    if isinstance(filename, int) or str(filename).isdigit():
        return int(filename)
    if os.path.isabs(filename) and os.path.exists(filename):
        return filename
    p1 = os.path.join(CURRENT_DIR, filename)
    if os.path.exists(p1):
        return p1
    p2 = os.path.join(PARENT_DIR, filename)
    if os.path.exists(p2):
        return p2
    return filename

# Thiết bị tính toán
if torch.backends.mps.is_available():
    DEVICE = "mps"
    DEVICE_NAME = "Apple Silicon GPU (MPS Metal)"
elif torch.cuda.is_available():
    DEVICE = "cuda"
    DEVICE_NAME = f"NVIDIA GPU ({torch.cuda.get_device_name(0)})"
else:
    DEVICE = "cpu"
    DEVICE_NAME = "CPU"

# =============================================================================
# 2. CƠ CHẾ GHI TELEMETRY ATOMIC WRITE CHO GAMA
# =============================================================================
def write_telemetry_atomic(data, target_paths=None):
    if target_paths is None:
        target_paths = JSON_TELEMETRY_PATHS
    elif isinstance(target_paths, str):
        target_paths = [target_paths]

    for target_path in target_paths:
        target_dir = os.path.dirname(os.path.abspath(target_path))
        if not os.path.exists(target_dir):
            continue
        try:
            fd, tmp_path = tempfile.mkstemp(prefix="roi_telemetry_", suffix=".tmp", dir=target_dir)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp_path, 0o644)
            os.replace(tmp_path, target_path)
        except Exception:
            pass

# =============================================================================
# 3. CÁC HÀM THUẬT TOÁN KHOA HỌC MAX-PRESSURE
# =============================================================================
def convert_roi_to_pixels(roi_points, frame_w, frame_h):
    """Chuyển đổi tọa độ ROI (tỉ lệ [0.0 - 1.0] hoặc pixel) sang mảng numpy pixel chuẩn."""
    pts = []
    for pt in roi_points:
        x, y = pt[0], pt[1]
        if x <= 1.0 and y <= 1.0:
            px = int(x * frame_w)
            py = int(y * frame_h)
        else:
            px = int(x)
            py = int(y)
        pts.append([px, py])
    return np.array(pts, dtype=np.int32)

def compute_stop_line_coord(roi_polygon_px, queue_axis):
    """Tự động suy luận tọa độ vạch dừng từ mép đa giác ROI."""
    if len(roi_polygon_px) == 0:
        return 0
    if queue_axis == "y":
        return int(np.max(roi_polygon_px[:, 1]))
    else:
        return int(np.max(roi_polygon_px[:, 0]))

def calculate_morphological_occupancy(frame_shape, dwelling_vehicles, roi_polygon_px, kernel_size):
    """
    Tính Mật độ chiếm dụng (Occupancy %) bằng mặt nạ hình thái học:
      1. Bounding box của xe dừng trong ROI.
      2. Phép giãn nở Dilation gộp cụm xe liên tục.
      3. AND bitwise với ROI mask: Đo tỉ lệ % pixel bị chiếm dụng thực tế.
    """
    h, w = frame_shape[:2]
    vehicle_mask = np.zeros((h, w), dtype=np.uint8)

    for v in dwelling_vehicles:
        x1, y1, x2, y2 = v["box"]
        x1 = max(0, min(w - 1, x1))
        y1 = max(0, min(h - 1, y1))
        x2 = max(0, min(w - 1, x2))
        y2 = max(0, min(h - 1, y2))
        cv2.rectangle(vehicle_mask, (x1, y1), (x2, y2), 255, -1)

    # Phép Dilation
    k = max(3, kernel_size | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
    dilated_mask = cv2.dilate(vehicle_mask, kernel, iterations=1)

    # ROI mask
    roi_mask = np.zeros((h, w), dtype=np.uint8)
    if len(roi_polygon_px) >= 3:
        cv2.fillPoly(roi_mask, [roi_polygon_px], 255)

    # Phép giao AND
    combined = cv2.bitwise_and(dilated_mask, roi_mask)
    roi_pixels = cv2.countNonZero(roi_mask)
    occupied_pixels = cv2.countNonZero(combined)

    occupancy = (occupied_pixels / roi_pixels * 100.0) if roi_pixels > 0 else 0.0
    return min(occupancy, 100.0), combined

def calculate_queue_length(dwelling_vehicles, stop_line_coord, queue_axis, pixel_to_meter, body_length):
    """Tính Chiều dài hàng đợi (Queue Length - Mét)."""
    if len(dwelling_vehicles) == 0:
        return 0.0

    if queue_axis == "y":
        positions = [v["bottom_center"][1] for v in dwelling_vehicles]
    else:
        positions = [v["bottom_center"][0] for v in dwelling_vehicles]

    max_dist_px = max(abs(pos - stop_line_coord) for pos in positions)
    length_m = (max_dist_px * pixel_to_meter) + body_length
    return round(length_m, 2)

# =============================================================================
# 4. CHƯƠNG TRÌNH CHÍNH
# =============================================================================
def parse_arguments():
    parser = argparse.ArgumentParser(description="Tính áp lực vùng ROI và đồng bộ Digital Twin")
    parser.add_argument("--source", type=str, choices=["1", "2"], default=None,
                        help="Nguồn: 1 = Video ROI, 2 = Live Camera")
    parser.add_argument("--video", type=str, default=DEFAULT_VIDEO,
                        help="Đường dẫn file video tùy chọn")
    parser.add_argument("--conf", type=float, default=CONF_THRESHOLD,
                        help="Ngưỡng confidence nhận diện")
    return parser.parse_args()

def load_roi_points():
    """Tự động tải tọa độ từ roi_config.json nếu có, ngược lại dùng mặc định."""
    if os.path.exists(JSON_CONFIG_PATH):
        try:
            with open(JSON_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                pts = data.get("points_normalized", [])
                if len(pts) >= 3:
                    print(f"✓ Đã nạp {len(pts)} điểm ROI từ file cấu hình: {JSON_CONFIG_PATH}")
                    return pts
        except Exception as e:
            print(f"⚠️ Không thể đọc {JSON_CONFIG_PATH}: {e}")
    
    print("✓ Sử dụng tọa độ ROI hiệu chuẩn mặc định của đề tài.")
    return ROI_POINTS_DEFAULT

def main():
    args = parse_arguments()

    if args.source is not None:
        choice = args.source
    else:
        print("\n" + "=" * 65)
        print("🚦 HỆ THỐNG DIGITAL TWIN: CHỌN NGUỒN TÍNH ÁP LỰC VÙNG ROI")
        print("=" * 65)
        print("  [1] Video mẫu thực nghiệm ROI (intersection_1_roi.mp4)")
        print("  [2] Live Camera / Webcam máy tính (0)")
        print("-" * 65)
        user_input = input("👉 Nhập lựa chọn của bạn (1 hoặc 2) [Mặc định: 1]: ").strip()
        choice = "2" if user_input == "2" else "1"

    if choice == "2":
        source_val = 0
        source_name = "Live Camera (0)"
    else:
        resolved_vid = resolve_file(args.video)
        source_val = resolved_vid
        source_name = os.path.basename(str(resolved_vid))

    print("\n" + "=" * 75)
    print("🚀 MODULE 2: TÍNH ÁP LỰC VÙNG ROI & ĐỒNG BỘ DIGITAL TWIN (MAX-PRESSURE)")
    print("=" * 75)
    print(f"✓ Thiết bị tính toán  : {DEVICE_NAME}")
    print(f"✓ Nguồn video         : {source_name}")
    print(f"✓ Cầu nối Telemetry   : {JSON_TELEMETRY_PATH}")

    # Tải mô hình YOLOv8
    model_path = None
    for m in MODEL_PREFERENCE:
        p = resolve_file(m)
        if os.path.exists(p):
            model_path = p
            break
    
    if not model_path:
        print(f"❌ Không tìm thấy trọng số YOLO nào trong {MODEL_PREFERENCE}!")
        return

    print(f"✓ Tải mô hình YOLO    : {model_path}")
    try:
        model = YOLO(model_path)
    except Exception as e:
        print(f"❌ Lỗi tải mô hình YOLO: {e}")
        return

    cap = cv2.VideoCapture(source_val)
    if not cap.isOpened():
        print(f"❌ Không thể mở video: {source_val}")
        return

    # Nạp tọa độ ROI
    roi_points = load_roi_points()

    print(f"✓ Trục hàng đợi       : {QUEUE_AXIS.upper()} ({'Dọc' if QUEUE_AXIS == 'y' else 'Ngang'})")
    print(f"✓ Hệ số quy đổi mét   : {PIXEL_TO_METER} m/pixel (1m ≈ {int(1/PIXEL_TO_METER)} px)")
    print("-" * 75)
    print("📌 Phím điều khiển:")
    print("   [m] : Bật/Tắt chế độ xem Mặt Nạ Hình Thái Học (Morphological Mask)")
    print("   [p] : Tạm dừng / Tiếp tục")
    print("   [s] : Chụp lưu ảnh snapshot minh chứng")
    print("   [q] : Thoát chương trình")
    print("=" * 75)

    is_paused = False
    show_mask_mode = False
    fps_counter = 0
    fps_timer = time.time()
    current_fps = 0.0

    track_history = collections.defaultdict(lambda: collections.deque(maxlen=20))
    dwell_counter = collections.defaultdict(int)

    while True:
        if not is_paused:
            ret, frame = cap.read()
            if not ret or frame is None:
                if LOOP_VIDEO and not isinstance(source_val, int):
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                else:
                    print("\n✅ Đã đọc hết video.")
                    break

            fh, fw = frame.shape[:2]
            if MAX_FRAME_WIDTH and fw > MAX_FRAME_WIDTH:
                scale = MAX_FRAME_WIDTH / fw
                frame = cv2.resize(frame, (MAX_FRAME_WIDTH, int(fh * scale)))
                fh, fw = frame.shape[:2]

            # Quy đổi tọa độ ROI và vạch dừng
            roi_polygon_px = convert_roi_to_pixels(roi_points, fw, fh)
            stop_line_coord = compute_stop_line_coord(roi_polygon_px, QUEUE_AXIS)

            # Chạy YOLO Tracking với ByteTrack
            try:
                results = model.track(
                    frame,
                    persist=True,
                    tracker="bytetrack.yaml",
                    conf=args.conf,
                    device=DEVICE,
                    verbose=False
                )
            except Exception:
                results = model(frame, conf=args.conf, device=DEVICE, verbose=False)

            tracked_vehicles = []
            dwelling_vehicles = []

            if results and len(results) > 0 and results[0].boxes is not None:
                boxes_obj = results[0].boxes
                has_id = boxes_obj.id is not None

                for i, box in enumerate(boxes_obj):
                    cls_id = int(box.cls[0].item())
                    raw_name = model.names.get(cls_id, str(cls_id)).lower()

                    if not any(k in raw_name for k in ["car", "motor", "bike", "bus", "truck"]):
                        continue

                    conf = float(box.conf[0].item())
                    x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                    track_id = int(boxes_obj.id[i].item()) if has_id else (1000 + i)

                    # Điểm tiếp đất chân xe
                    cx = int((x1 + x2) / 2)
                    cy = int(y2)

                    # Kiểm tra điểm chân xe nằm trong đa giác ROI
                    in_roi = False
                    if len(roi_polygon_px) >= 3:
                        contour = roi_polygon_px.reshape((-1, 1, 2)).astype(np.float32)
                        in_roi = cv2.pointPolygonTest(contour, (float(cx), float(cy)), False) >= 0

                    # Vận tốc pixel
                    history = track_history[track_id]
                    history.append((cx, cy))
                    speed_px = 0.0
                    if len(history) >= 2:
                        dx = history[-1][0] - history[-2][0]
                        dy = history[-1][1] - history[-2][1]
                        speed_px = math.sqrt(dx * dx + dy * dy)

                    # Xe dừng chờ trong ROI nếu vận tốc < 3px/frame
                    if in_roi and speed_px < 3.0:
                        dwell_counter[track_id] += 1
                    else:
                        dwell_counter[track_id] = max(0, dwell_counter[track_id] - 1)

                    is_dwelling = dwell_counter[track_id] >= DWELLING_FRAMES_THRESH

                    v_info = {
                        "id": track_id,
                        "box": (x1, y1, x2, y2),
                        "bottom_center": (cx, cy),
                        "in_roi": in_roi,
                        "is_dwelling": is_dwelling
                    }
                    tracked_vehicles.append(v_info)
                    if in_roi and is_dwelling:
                        dwelling_vehicles.append(v_info)

            # Tính toán các chỉ số khoa học:
            occupancy_pct, combined_mask = calculate_morphological_occupancy(
                frame.shape, dwelling_vehicles, roi_polygon_px, MORPH_KERNEL_SIZE
            )
            queue_len_m = calculate_queue_length(
                dwelling_vehicles, stop_line_coord, QUEUE_AXIS, PIXEL_TO_METER, VEHICLE_BODY_LENGTH_M
            )
            pressure_score = round(occupancy_pct * queue_len_m, 1)

            # Đánh giá mức độ ùn tắc
            if pressure_score < 120:
                traffic_status = "THONG THOANG"
                status_code = 1
                status_color = (16, 185, 129)   # Xanh lá
            elif pressure_score < 350:
                traffic_status = "DONG DUC"
                status_code = 2
                status_color = (245, 158, 11)   # Vàng cam
            else:
                traffic_status = "UN TAC"
                status_code = 3
                status_color = (239, 68, 68)    # Đỏ cảnh báo

            # -----------------------------------------------------------------
            # Xuất Telemetry thời gian thực (Atomic Write)
            # -----------------------------------------------------------------
            telemetry_data = {
                "timestamp": round(time.time(), 2),
                "source_type": "camera" if isinstance(source_val, int) else "video",
                "source_name": source_name,
                "fps": round(current_fps, 1),
                "roi_polygon": [[round(pt[0], 3), round(pt[1], 3)] for pt in roi_points],
                "roi_occupancy_pct": round(occupancy_pct, 1),
                "queue_length_m": queue_len_m,
                "pressure_score": pressure_score,
                "status": traffic_status,
                "status_code": status_code,
                "vehicles_in_roi": sum(1 for v in tracked_vehicles if v["in_roi"]),
                "dwelling_vehicles": len(dwelling_vehicles)
            }
            write_telemetry_atomic(telemetry_data)

            # -----------------------------------------------------------------
            # TRỰC QUAN HÓA FRAME
            # -----------------------------------------------------------------
            # 1. Vẽ đa giác ROI phủ màu bán trong suốt
            if len(roi_polygon_px) >= 3:
                overlay = frame.copy()
                cv2.fillPoly(overlay, [roi_polygon_px], (255, 220, 100))
                cv2.addWeighted(overlay, 0.22, frame, 0.78, 0, frame)
                cv2.polylines(frame, [roi_polygon_px], isClosed=True, color=(255, 140, 0), thickness=2)

            # 2. Vẽ Vạch dừng (Stop Line)
            if stop_line_coord > 0:
                if QUEUE_AXIS == "y":
                    cv2.line(frame, (0, stop_line_coord), (fw, stop_line_coord), (0, 0, 255), 2)
                    cv2.putText(frame, "STOP LINE", (15, stop_line_coord - 8),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                else:
                    cv2.line(frame, (stop_line_coord, 0), (stop_line_coord, fh), (0, 0, 255), 2)
                    cv2.putText(frame, "STOP LINE", (stop_line_coord + 8, 25),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

            # 3. Vẽ Bounding Boxes các xe
            for v in tracked_vehicles:
                x1, y1, x2, y2 = v["box"]
                tid = v["id"]
                if v["in_roi"]:
                    if v["is_dwelling"]:
                        box_col = (0, 0, 255)       # Đỏ: Xe đang xếp hàng chờ
                        tag = f"#{tid} QUEUE"
                    else:
                        box_col = (0, 165, 255)     # Cam: Xe đang di chuyển trong ROI
                        tag = f"#{tid} IN-ROI"
                else:
                    box_col = (180, 180, 180)       # Xám: Xe ngoài ROI
                    tag = f"#{tid}"

                cv2.rectangle(frame, (x1, y1), (x2, y2), box_col, 2)
                cv2.circle(frame, v["bottom_center"], 4, box_col, -1)
                cv2.putText(frame, tag, (x1, max(14, y1 - 5)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.42, box_col, 1)

            # FPS
            fps_counter += 1
            now = time.time()
            if now - fps_timer >= 0.5:
                current_fps = fps_counter / (now - fps_timer)
                fps_counter = 0
                fps_timer = now

            # 4. Vẽ Bảng HUD hiển thị kết quả Áp Lực Vùng ROI
            hud_w, hud_h = 330, 215
            overlay_hud = frame.copy()
            cv2.rectangle(overlay_hud, (15, 15), (15 + hud_w, 15 + hud_h), (255, 255, 255), -1)
            cv2.addWeighted(overlay_hud, 0.88, frame, 0.12, 0, frame)
            cv2.rectangle(frame, (15, 15), (15 + hud_w, 15 + hud_h), (200, 200, 200), 1)

            cv2.putText(frame, "DIGITAL TWIN: AP LUC VUNG ROI", (25, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (15, 23, 42), 2)
            cv2.putText(frame, f"FPS: {current_fps:.1f}", (255, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (100, 116, 139), 1)
            cv2.line(frame, (25, 48), (15 + hud_w - 10, 48), (220, 220, 220), 1)

            cv2.putText(frame, f"1. Mat do (Occupancy): {occupancy_pct:.1f}%", (25, 75),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (37, 99, 235), 2)
            cv2.putText(frame, f"2. Hang doi (Queue):    {queue_len_m:.1f} m", (25, 105),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (217, 119, 6), 2)
            cv2.putText(frame, f"3. AP LUC (PRESSURE):   {pressure_score:.1f}", (25, 138),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 38, 38), 2)

            cv2.putText(frame, "4. Trang thai:", (25, 170),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (51, 65, 85), 1)
            cv2.putText(frame, traffic_status, (140, 170),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, status_color, 2)

            cv2.putText(frame, "[m] Xem Mask | [p] Pause | [s] Chup | [q] Thoat", (25, 200),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (100, 116, 139), 1)

            # Chuẩn bị frame xem Mask nếu người dùng bấm 'm'
            mask_bgr = cv2.cvtColor(combined_mask, cv2.COLOR_GRAY2BGR)
            mask_bgr[:, :, 0] = 0
            mask_bgr[:, :, 2] = 0
            if len(roi_polygon_px) >= 3:
                cv2.polylines(mask_bgr, [roi_polygon_px], isClosed=True, color=(100, 100, 255), thickness=1)
            cv2.putText(mask_bgr, f"MORPHOLOGICAL MASK (Occupancy: {occupancy_pct:.1f}%)", (20, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            active_display = mask_bgr if show_mask_mode else frame

        cv2.imshow("Module 2 - Digital Twin ROI Pressure (Max-Pressure)", active_display)

        key = cv2.waitKey(20 if not is_paused else 100) & 0xFF
        if key == ord('q') or key == 27:
            print("\n✅ Đã thoát chương trình.")
            break
        elif key == ord('p') or key == 32:
            is_paused = not is_paused
            status_str = "TẠM DỪNG" if is_paused else "TIẾP TỤC"
            print(f"⏸ Trạng thái: {status_str}")
        elif key == ord('m'):
            show_mask_mode = not show_mask_mode
            mode_str = "MẶT NẠ DILATION (MASK)" if show_mask_mode else "VIDEO + ROI OVERLAY"
            print(f"🔄 Chế độ xem: {mode_str}")
        elif key == ord('s'):
            snapshot_name = f"snapshot_roi_{int(time.time())}.jpg"
            snapshot_path = os.path.join(CURRENT_DIR, snapshot_name)
            cv2.imwrite(snapshot_path, active_display)
            print(f"📷 Đã lưu ảnh minh chứng áp lực: {snapshot_path}")

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
