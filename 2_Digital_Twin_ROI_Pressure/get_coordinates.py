#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
ĐỀ TÀI NCKH: DIGITAL TWIN - ĐIỀU KHIỂN TÍN HIỆU GIAO THÔNG THÍCH ỨNG
FOLDER 2: CÔNG CỤ TƯƠNG TÁC LẤY TỌA ĐỘ VÙNG ROI (GET COORDINATES)
=============================================================================
Mô tả kỹ thuật:
  - Cho phép Hội đồng hoặc người dùng nhấp chuột trực tiếp trên khung hình video/camera
    để xác định các đỉnh đa giác của Vùng quan tâm (ROI - Region of Interest).
  - Tự động chuẩn hóa tọa độ theo tỉ lệ phần trăm [0.0 - 1.0] để tương thích với
    mọi kích thước màn hình và không gian mô phỏng GAMA.
  - Tự động xuất mã định dạng Python và GAML ra Terminal.
  - Tự động lưu cấu hình ra file 'roi_config.json' để file 'calculate_roi_pressure.py'
    và GAMA có thể nạp trực tiếp mà không cần sửa mã nguồn.

Hướng dẫn sử dụng:
  python get_coordinates.py
  - Nhấp CHUỘT TRÁI để chọn từng đỉnh đa giác ROI.
  - Phím 'p': In đoạn mã Python và GAML ra màn hình Terminal.
  - Phím 's': Lưu cấu hình vào file 'roi_config.json'.
  - Phím 'c': Xóa tất cả các điểm và vẽ lại.
  - Phím 'q' hoặc ESC: Lưu cấu hình và thoát.
=============================================================================
"""

import os
import sys
import json
import argparse
import cv2

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)

DEFAULT_VIDEO = "intersection_1_roi.mp4"
JSON_CONFIG_PATH = os.path.join(CURRENT_DIR, "roi_config.json")

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

coordinates_px = []
coordinates_norm = []
original_frame = None
display_frame = None
frame_w, frame_h = 0, 0
source_label = ""

def redraw_canvas():
    global display_frame
    display_frame = original_frame.copy()
    num_pts = len(coordinates_px)

    # Vẽ các điểm và đường nối
    for i in range(num_pts):
        x, y = coordinates_px[i]
        cv2.circle(display_frame, (x, y), 5, (0, 0, 255), -1)
        cv2.circle(display_frame, (x, y), 7, (255, 255, 255), 2)

        fx, fy = coordinates_norm[i]
        lbl = f"P{i+1}: [{fx:.2f}, {fy:.2f}]"
        cv2.putText(display_frame, lbl, (x + 8, y - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 255), 1)

        if i > 0:
            prev_x, prev_y = coordinates_px[i - 1]
            cv2.line(display_frame, (prev_x, prev_y), (x, y), (255, 140, 0), 2)

    # Đóng kín đa giác nếu >= 3 điểm
    if num_pts >= 3:
        cv2.line(display_frame, (coordinates_px[-1][0], coordinates_px[-1][1]),
                 (coordinates_px[0][0], coordinates_px[0][1]), (0, 255, 0), 2)

    # Vẽ bảng hướng dẫn trên frame
    cv2.rectangle(display_frame, (10, 10), (520, 80), (15, 23, 42), -1)
    cv2.rectangle(display_frame, (10, 10), (520, 80), (56, 189, 248), 1)
    cv2.putText(display_frame, f"DA CHON: {num_pts} DIEM ROI | Nguon: {source_label}", (20, 34),
                cv2.FONT_HERSHEY_SIMPLEX, 0.52, (250, 204, 21), 2)
    cv2.putText(display_frame, "[Click] Them diem | [p] In code | [s] Luu file | [c] Ve lai | [q] Thoat", (20, 62),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)

def click_event(event, x, y, flags, params):
    global coordinates_px, coordinates_norm
    if event == cv2.EVENT_LBUTTONDOWN:
        fx = round(x / frame_w, 3)
        fy = round(y / frame_h, 3)
        coordinates_px.append([x, y])
        coordinates_norm.append([fx, fy])

        print(f"👉 Điểm P{len(coordinates_px)}: Pixel=[{x}, {y}] | Chuẩn hóa=[{fx:.3f}, {fy:.3f}]")
        redraw_canvas()
        cv2.imshow("Cong Cu Lay Toa Do ROI (Get Coordinates)", display_frame)

def print_formatted_code():
    print("\n" + "=" * 65)
    print("📋 ĐOẠN CODE ĐỊNH DẠNG SẴN ĐỂ SỬ DỤNG TRONG DỰ ÁN:")
    print("=" * 65)
    print("# 1. Định dạng Python (Tọa độ tỉ lệ % chuẩn hóa):")
    print("ROI_POINTS = [")
    for pt in coordinates_norm:
        print(f"    ({pt[0]}, {pt[1]}),")
    print("]")
    print("\n# 2. Định dạng GAML (GAMA Platform):")
    points_gaml = ", ".join([f"{{{pt[0]} * shape.width, {pt[1]} * shape.height}}" for pt in coordinates_norm])
    print(f"geometry roi_shape <- polygon([{points_gaml}]);")
    print("=" * 65 + "\n")

def save_json_config():
    if len(coordinates_norm) < 3:
        print("⚠️ Cần chọn ít nhất 3 điểm để tạo đa giác ROI trước khi lưu.")
        return False
    data = {
        "source": source_label,
        "resolution": {"width": frame_w, "height": frame_h},
        "points_normalized": coordinates_norm,
        "points_pixel": coordinates_px
    }
    with open(JSON_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"💾 ĐÃ LƯU CẤU HÌNH ROI THÀNH CÔNG VÀO: {JSON_CONFIG_PATH}")
    return True

def parse_args():
    parser = argparse.ArgumentParser(description="Tool lấy tọa độ vùng ROI tương tác")
    parser.add_argument("--source", type=str, choices=["1", "2"], default=None,
                        help="Nguồn: 1 = Video ROI, 2 = Live Camera")
    parser.add_argument("--video", type=str, default=DEFAULT_VIDEO,
                        help="Đường dẫn video tùy chọn")
    return parser.parse_args()

def main():
    global original_frame, display_frame, frame_w, frame_h, source_label

    args = parse_args()
    if args.source is not None:
        choice = args.source
    else:
        print("\n" + "=" * 65)
        print("🛠️  CÔNG CỤ LẤY TỌA ĐỘ VÙNG ROI: CHỌN NGUỒN")
        print("=" * 65)
        print("  [1] Video mẫu thực nghiệm ROI (intersection_1_roi.mp4)")
        print("  [2] Live Camera / Webcam máy tính (0)")
        print("-" * 65)
        user_input = input("👉 Nhập lựa chọn của bạn (1 hoặc 2) [Mặc định: 1]: ").strip()
        choice = "2" if user_input == "2" else "1"

    if choice == "2":
        source_val = 0
        source_label = "Live Camera (0)"
    else:
        resolved_vid = resolve_file(args.video)
        source_val = resolved_vid
        source_label = os.path.basename(str(resolved_vid))

    print(f"✓ Đang mở nguồn: {source_label}")
    cap = cv2.VideoCapture(source_val)
    if not cap.isOpened():
        print(f"❌ Không thể mở nguồn video: {source_val}")
        return

    # Lấy frame mẫu
    if isinstance(source_val, int):
        for _ in range(10):  # Bỏ vài frame đầu webcam để cân bằng sáng
            cap.read()
    success, original_frame = cap.read()
    cap.release()

    if not success or original_frame is None:
        print("❌ Không thể đọc khung hình từ nguồn.")
        return

    frame_h, frame_w = original_frame.shape[:2]
    # Thu nhỏ nếu độ phân giải quá lớn để vừa màn hình thao tác
    if frame_w > 1080:
        scale = 1080 / frame_w
        original_frame = cv2.resize(original_frame, (1080, int(frame_h * scale)))
        frame_h, frame_w = original_frame.shape[:2]

    redraw_canvas()

    print(f"✓ Kích thước khung hình thao tác: {frame_w}x{frame_h} px")
    print("📌 HƯỚNG DẪN:")
    print("   1. Nhấp CHUỘT TRÁI để đánh dấu từng góc của đa giác ROI.")
    print("   2. Nhấn phím 'p' để in code Python/GAML ra Terminal.")
    print("   3. Nhấn phím 's' để lưu vào file 'roi_config.json'.")
    print("   4. Nhấn phím 'c' để xóa và vẽ lại từ đầu.")
    print("   5. Nhấn phím 'q' hoặc ESC để hoàn tất và thoát.")
    print("=" * 65)

    window_name = "Cong Cu Lay Toa Do ROI (Get Coordinates)"
    cv2.namedWindow(window_name)
    cv2.setMouseCallback(window_name, click_event)

    while True:
        cv2.imshow(window_name, display_frame)
        key = cv2.waitKey(20) & 0xFF

        if key == ord('q') or key == 27:
            if len(coordinates_norm) >= 3:
                save_json_config()
                print_formatted_code()
            print("✅ Đã kết thúc công cụ lấy tọa độ ROI.")
            break
        elif key == ord('p'):
            print_formatted_code()
        elif key == ord('s'):
            save_json_config()
        elif key == ord('c'):
            coordinates_px.clear()
            coordinates_norm.clear()
            print("↺ Đã xóa tất cả các điểm ROI. Mời nhấp chuột vẽ lại.")
            redraw_canvas()

    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
