#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
ĐỀ TÀI NCKH: DIGITAL TWIN - ĐIỀU KHIỂN TÍN HIỆU GIAO THÔNG THÍCH ỨNG
FOLDER 1: NHẬN DIỆN XE THỜI GIAN THỰC & ĐỒNG BỘ DIGITAL TWIN (YOLOv8 -> JSON -> GAMA)
=============================================================================
Mô tả kỹ thuật:
  1. Hỗ trợ 2 nguồn dữ liệu:
     - Type 1: Video mẫu thực nghiệm có sẵn (intersection_1_vehicles.mp4)
     - Type 2: Live Camera / Webcam trực tiếp (0)
  2. Ứng dụng YOLOv8 kết hợp thuật toán ByteTrack Multi-Object Tracking để gán ID
     ổn định cho từng phương tiện (Car, Motorcycle, Bus, Truck).
  3. Lọc điểm tiếp đất bánh xe (Bottom-Edge Grounding) và chuẩn hóa tọa độ [0.0 - 1.0].
  4. Cơ chế Atomic Write: Ghi liên tục dữ liệu sang file 'live_traffic.json'
     (qua file tạm .tmp rồi atomic rename), loại trừ hoàn toàn xung đột khi GAMA đọc live.
  5. Cung cấp dữ liệu tức thì cho mô hình GAMA Platform để sinh tác tử xe song sinh.

Hướng dẫn chạy:
  python detect_and_sync.py
  (Hoặc truyền tham số: python detect_and_sync.py --source 1 hoặc --source 2)
=============================================================================
"""

import os
import sys
import time
import json
import math
import argparse
import tempfile
import collections
import cv2
import torch
from ultralytics import YOLO

# =============================================================================
# 1. CẤU HÌNH & TỰ ĐỘNG PHÁT HIỆN ĐƯỜNG DẪN
# =============================================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)

DEFAULT_VIDEO = "intersection_1_vehicles.mp4"
MODEL_PREFERENCE = ["yolov8s.pt", "yolov8n.pt"]
JSON_OUTPUT_FILES = [
    os.path.join(CURRENT_DIR, "live_traffic.json"),
    os.path.join(CURRENT_DIR, "gama_trafficsi_twin", "live_traffic.json"),
]
JSON_OUTPUT_FILE = JSON_OUTPUT_FILES[0]

# Ngưỡng tin cậy nhận diện
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

# Tự động chọn thiết bị tăng tốc phần cứng
if torch.backends.mps.is_available():
    DEVICE = "mps"
    DEVICE_NAME = "Apple Silicon GPU (MPS Metal)"
elif torch.cuda.is_available():
    DEVICE = "cuda"
    DEVICE_NAME = f"NVIDIA GPU ({torch.cuda.get_device_name(0)})"
else:
    DEVICE = "cpu"
    DEVICE_NAME = "CPU"

# Bảng màu hiển thị (BGR)
CLASS_COLORS = {
    "car": (245, 130, 32),        # Xanh dương đậm
    "motorcycle": (50, 205, 50),   # Xanh lá cây chanh
    "bus": (0, 215, 255),          # Vàng hổ phách
    "truck": (30, 105, 255),       # Đỏ cam
}

CLASS_NAMES_VI = {
    "car": "O to",
    "motorcycle": "Xe may",
    "bus": "Xe buyt",
    "truck": "Xe tai"
}

# =============================================================================
# 2. CƠ CHẾ GHI FILE ATOMIC WRITE CHO DIGITAL TWIN
# =============================================================================
def write_json_atomic(data, target_paths=None):
    """
    Ghi dữ liệu JSON an toàn bằng Atomic Write (Tạo file tạm -> flush -> fsync -> rename).
    Ghi đồng bộ ra cả thư mục chính và thư mục dự án GAMA (gama_vehicle_twin).
    """
    if target_paths is None:
        target_paths = JSON_OUTPUT_FILES
    elif isinstance(target_paths, str):
        target_paths = [target_paths]

    for target_path in target_paths:
        target_dir = os.path.dirname(os.path.abspath(target_path))
        if not os.path.exists(target_dir):
            continue
        try:
            fd, tmp_path = tempfile.mkstemp(prefix="live_sync_", suffix=".tmp", dir=target_dir)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, target_path)
        except Exception:
            pass

# =============================================================================
# 3. CHƯƠNG TRÌNH CHÍNH
# =============================================================================
def parse_arguments():
    parser = argparse.ArgumentParser(description="Digital Twin - YOLO Vehicle Detection & Live Sync")
    parser.add_argument("--source", type=str, choices=["1", "2"], default=None,
                        help="Nguồn dữ liệu: 1 = Video mẫu, 2 = Live Camera")
    parser.add_argument("--video", type=str, default=DEFAULT_VIDEO,
                        help="Đường dẫn file video tùy chọn (nếu chọn nguồn 1)")
    parser.add_argument("--conf", type=float, default=CONF_THRESHOLD,
                        help="Ngưỡng confidence nhận diện (mặc định 0.35)")
    return parser.parse_args()

def choose_source_interactive(args):
    """Hỏi người dùng lựa chọn nguồn nếu chưa truyền tham số dòng lệnh."""
    if args.source is not None:
        choice = args.source
    else:
        print("\n" + "=" * 65)
        print("🚦 HỆ THỐNG DIGITAL TWIN: CHỌN NGUỒN DỮ LIỆU ĐẦU VÀO")
        print("=" * 65)
        print("  [1] Video mẫu thực nghiệm có sẵn (intersection_1_vehicles.mp4)")
        print("  [2] Live Camera / Webcam máy tính (Camera 0)")
        print("-" * 65)
        user_input = input("👉 Nhập lựa chọn của bạn (1 hoặc 2) [Mặc định: 1]: ").strip()
        if user_input == "2":
            choice = "2"
        else:
            choice = "1"

    if choice == "2":
        source_val = 0
        source_name = "Live Camera (Webcam 0)"
    else:
        resolved_vid = resolve_file(args.video)
        source_val = resolved_vid
        source_name = os.path.basename(str(resolved_vid))
    
    return source_val, source_name

def main():
    args = parse_arguments()
    source_val, source_name = choose_source_interactive(args)

    print("\n" + "=" * 70)
    print("🚀 MODULE 1: NHẬN DIỆN XE THỜI GIAN THỰC & ĐỒNG BỘ DIGITAL TWIN")
    print("=" * 70)
    print(f"✓ Thiết bị tính toán  : {DEVICE_NAME}")
    print(f"✓ Nguồn video         : {source_name}")
    print(f"✓ Cầu nối dữ liệu JSON: {JSON_OUTPUT_FILE}")

    # Tìm và tải mô hình YOLOv8
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

    # Mở VideoCapture
    cap = cv2.VideoCapture(source_val)
    if not cap.isOpened():
        print(f"❌ Không thể mở nguồn video: {source_val}")
        return

    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    src_fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"✓ Độ phân giải gốc    : {src_w}x{src_h} | FPS: {src_fps:.1f}")
    print("-" * 70)
    print("📌 Phím điều khiển:")
    print("   [q] / [ESC] : Thoát chương trình")
    print("   [p] / Space : Tạm dừng / Tiếp tục video")
    print("   [s]         : Chụp lưu ảnh snapshot minh chứng")
    print("=" * 70)

    is_paused = False
    display_frame = None
    fps_counter = 0
    fps_timer = time.time()
    current_fps = 0.0
    session_id = int(time.time())

    track_history = collections.defaultdict(lambda: collections.deque(maxlen=10))

    try:
        while True:
            if is_paused:
                if display_frame is not None:
                    cv2.imshow("Module 1 - Digital Twin Vehicle Detection (YOLOv8)", display_frame)
                key = cv2.waitKey(50) & 0xFF
                if key == ord('q') or key == 27:
                    print("\n✅ Đã thoát chương trình.")
                    break
                elif key == ord('p') or key == 32:
                    is_paused = not is_paused
                    status_str = "TẠM DỪNG" if is_paused else "TIẾP TỤC"
                    print(f"⏸ Trạng thái video: {status_str}")
                elif key == ord('s') and display_frame is not None:
                    snapshot_name = f"snapshot_vehicle_sync_{int(time.time())}.jpg"
                    snapshot_path = os.path.join(CURRENT_DIR, snapshot_name)
                    cv2.imwrite(snapshot_path, display_frame)
                    print(f"📷 Đã lưu ảnh chụp màn hình: {snapshot_path}")
                continue

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

            # Chạy YOLO Multi-Object Tracking (ByteTrack)
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

            counts = {"car": 0, "motorcycle": 0, "bus": 0, "truck": 0}
            total_vehicles = 0
            vehicles_payload = []

            if results and len(results) > 0 and results[0].boxes is not None:
                boxes_obj = results[0].boxes
                has_id = boxes_obj.id is not None

                for i, box in enumerate(boxes_obj):
                    cls_id = int(box.cls[0].item())
                    raw_name = model.names.get(cls_id, str(cls_id)).lower()

                    # Chuẩn hóa tên lớp phương tiện
                    c_class = None
                    if "motor" in raw_name or "bike" in raw_name:
                        c_class = "motorcycle"
                    elif "car" in raw_name:
                        c_class = "car"
                    elif "bus" in raw_name:
                        c_class = "bus"
                    elif "truck" in raw_name:
                        c_class = "truck"

                    if c_class is None:
                        continue

                    counts[c_class] += 1
                    total_vehicles += 1
                    conf = float(box.conf[0].item())
                    x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                    track_id = int(boxes_obj.id[i].item()) if has_id else (1000 + i)

                    # Điểm tiếp đất chân xe (Bottom-center grounding point)
                    cx = int((x1 + x2) / 2)
                    cy = int(y2)

                    # Tọa độ chuẩn hóa theo tỉ lệ [0.0 - 1.0] cho GAMA
                    norm_x = round(cx / fw, 3)
                    norm_y = round(cy / fh, 3)

                    # Tính vận tốc pixel
                    history = track_history[track_id]
                    history.append((cx, cy))
                    speed_px = 0.0
                    if len(history) >= 2:
                        dx = history[-1][0] - history[-2][0]
                        dy = history[-1][1] - history[-2][1]
                        speed_px = round(math.sqrt(dx * dx + dy * dy), 1)

                    # Thêm vào payload JSON cho GAMA
                    vehicles_payload.append({
                        "id": track_id,
                        "class": c_class,
                        "class_name": c_class,
                        "norm_x": norm_x,
                        "norm_y": norm_y,
                        "speed_px": speed_px
                    })

                    # Vẽ Bounding Box và Label
                    color = CLASS_COLORS.get(c_class, (0, 255, 0))
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    cv2.circle(frame, (cx, cy), 4, (0, 0, 255), -1)

                    label_text = f"#{track_id} {CLASS_NAMES_VI[c_class]}: {conf*100:.0f}%"
                    (tw, th), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
                    cv2.rectangle(frame, (x1, max(0, y1 - th - 6)), (x1 + tw + 6, y1), color, -1)
                    cv2.putText(frame, label_text, (x1 + 3, max(th, y1 - 4)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 1)

            # Tính toán FPS hiển thị
            fps_counter += 1
            now = time.time()
            if now - fps_timer >= 0.5:
                current_fps = fps_counter / (now - fps_timer)
                fps_counter = 0
                fps_timer = now

            # -----------------------------------------------------------------
            # Xuất JSON thời gian thực (Atomic Write)
            # -----------------------------------------------------------------
            sync_payload = {
                "status": "running",
                "active": True,
                "session_id": session_id,
                "timestamp": round(time.time(), 2),
                "total_detected": total_vehicles,
                "source_type": "camera" if isinstance(source_val, int) else "video",
                "source_name": source_name,
                "fps": round(current_fps, 1),
                "counts": {
                    "total": total_vehicles,
                    "car": counts["car"],
                    "motorcycle": counts["motorcycle"],
                    "bus": counts["bus"],
                    "truck": counts["truck"]
                },
                "vehicles": vehicles_payload
            }
            write_json_atomic(sync_payload)

            # -----------------------------------------------------------------
            # Vẽ Bảng Thông Số HUD (Head-Up Display)
            # -----------------------------------------------------------------
            hud_w, hud_h = 310, 180
            overlay = frame.copy()
            cv2.rectangle(overlay, (15, 15), (15 + hud_w, 15 + hud_h), (255, 255, 255), -1)
            cv2.addWeighted(overlay, 0.88, frame, 0.12, 0, frame)
            cv2.rectangle(frame, (15, 15), (15 + hud_w, 15 + hud_h), (200, 200, 200), 1)

            cv2.putText(frame, "DIGITAL TWIN: NHAN DIEN XE", (25, 38),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (15, 23, 42), 2)
            cv2.line(frame, (25, 46), (15 + hud_w - 10, 46), (220, 220, 220), 1)

            cv2.putText(frame, f"Tong so xe: {total_vehicles}", (25, 68),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.52, (37, 99, 235), 2)
            cv2.putText(frame, f"FPS: {current_fps:.1f}", (210, 68),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (16, 185, 129), 2)

            line_y = 94
            cv2.putText(frame, f"- O to (Car): {counts['car']}", (25, line_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (51, 65, 85), 1)
            cv2.putText(frame, f"- Xe may: {counts['motorcycle']}", (170, line_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (51, 65, 85), 1)

            line_y += 24
            cv2.putText(frame, f"- Xe buyt: {counts['bus']}", (25, line_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (51, 65, 85), 1)
            cv2.putText(frame, f"- Xe tai: {counts['truck']}", (170, line_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (51, 65, 85), 1)

            line_y += 26
            cv2.putText(frame, "Bridge: live_traffic.json (SYNC)", (25, line_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, (16, 185, 129), 1)
            cv2.putText(frame, f"Thiet bi: {DEVICE.upper()}", (25, line_y + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (100, 116, 139), 1)

            display_frame = frame

            cv2.imshow("Module 1 - Digital Twin Vehicle Detection (YOLOv8)", display_frame)

            key = cv2.waitKey(20) & 0xFF
            if key == ord('q') or key == 27:
                print("\n✅ Đã thoát chương trình.")
                break
            elif key == ord('p') or key == 32:
                is_paused = not is_paused
                status_str = "TẠM DỪNG" if is_paused else "TIẾP TỤC"
                print(f"⏸ Trạng thái video: {status_str}")
            elif key == ord('s'):
                snapshot_name = f"snapshot_vehicle_sync_{int(time.time())}.jpg"
                snapshot_path = os.path.join(CURRENT_DIR, snapshot_name)
                cv2.imwrite(snapshot_path, display_frame)
                print(f"📷 Đã lưu ảnh chụp màn hình: {snapshot_path}")

    finally:
        cap.release()
        cv2.destroyAllWindows()
        
        # Ghi trạng thái dừng để GAMA không sinh xe khi YOLO chưa bật
        stopped_payload = {
            "status": "stopped",
            "active": False,
            "session_id": session_id,
            "timestamp": round(time.time(), 2),
            "total_detected": 0,
            "source_type": "camera" if isinstance(source_val, int) else "video",
            "source_name": source_name,
            "fps": 0.0,
            "counts": {"total": 0, "car": 0, "motorcycle": 0, "bus": 0, "truck": 0},
            "vehicles": []
        }
        write_json_atomic(stopped_payload)
        print("🛑 Đã dừng đồng bộ live traffic.json cho GAMA.")

if __name__ == "__main__":
    main()
