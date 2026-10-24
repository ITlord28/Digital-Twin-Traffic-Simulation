# HƯỚNG DẪN KIỂM THỬ: DIGITAL TWIN VEHICLE DETECTION (YOLOv8 -> GAMA)

Thư mục này phục vụ kiểm chứng năng lực **Digital Twin (Bản sao số)** trong việc nhận diện và ánh xạ phương tiện giao thông thời gian thực từ Computer Vision sang mô phỏng Agent-Based GAMA tại nút giao Cần Thơ.

---

## 1. Cấu Trúc Thành Phần
| Tệp / Thư mục | Chức năng kỹ thuật |
| :--- | :--- |
| **`detect_and_sync.py`** | Script Python chạy YOLOv8 + ByteTrack nhận diện xe, phân loại 4 nhóm phương tiện, tính tọa độ chân xe và xuất JSON. |
| **`live_traffic.json`** | File dữ liệu cầu nối đồng bộ thời gian thực bằng cơ chế Atomic Write. |
| **`yolov8n.pt`** | Trọng số mô hình YOLOv8 nạp sẵn (hỗ trợ tự nhận `yolov8s.pt` nếu có). |
| **`gama_trafficsi_twin/`** | **Dự án GAMA Digital Twin (Bản đồ GIS thực tế TrafficSi)**: Dự án GAMA độc lập sử dụng tập GIS `road.shp`, `building.shp`, `traffic_light.shp` tại ngã tư Nguyễn Văn Cừ - Nguyễn Văn Linh (Cần Thơ) từ TrafficSi. Đồng bộ trực tiếp từ YOLO. |

---

## 2. Các Bước Thực Hiện Kiểm Thử

### 🔹 Bước 1: Khởi động Python YOLO Detector
Mở Terminal tại thư mục này và chạy:
```bash
python detect_and_sync.py
```
*(Hoặc `python3 detect_and_sync.py`)*

*Lưu ý: `detect_and_sync.py` tự động ghi đồng bộ dữ liệu song song vào `live_traffic.json` và `gama_trafficsi_twin/live_traffic.json`.*

Hệ thống sẽ hiển thị menu chọn nguồn dữ liệu:
- Nhấn phím `1` (hoặc Enter): Chạy với video thực nghiệm mẫu (`intersection_1_vehicles.mp4`).
- Nhấn phím `2`: Chạy với Live Camera / Webcam máy tính (Camera 0).

*(Hoặc có thể chỉ định trực tiếp qua cờ lệnh: `python detect_and_sync.py --source 1` hoặc `--source 2`).*

**Phím tắt điều khiển cửa sổ OpenCV**:
- `p` hoặc phím `Space`: Tạm dừng / Tiếp tục video.
- `s`: Lưu ảnh chụp màn hình (Snapshot).
- `q` hoặc phím `ESC`: Thoát chương trình.

---

### 🔹 Bước 2: Khởi động Mô Phỏng GAMA Platform
1. Trong GAMA Platform: **File -> Import... -> General -> Existing Projects into Workspace** -> Trỏ Browse tới thư mục:
   `1_Digital_Twin_Vehicle_Detection/gama_trafficsi_twin` -> Bấm **Finish**.
2. Trong Navigator, mở thư mục `models/` -> Mở file `CanTho_TrafficSi_Digital_Twin.gaml`.
3. Bấm nút màu xanh **CanThoTrafficSiExperiment** trên thanh công cụ để chạy mô phỏng.

---

## 3. Tiêu Chí Đánh Giá Tính Năng Digital Twin
1. **Đồng bộ thực thể 1-1**:
   - Khi xe mới xuất hiện trong video/webcam $\rightarrow$ Tác tử mới ngay lập tức xuất hiện tại vị trí tương ứng trên mặt đường nút giao Cần Thơ trong GAMA.
   - Khi xe rời khỏi góc nhìn camera $\rightarrow$ Tác tử trong GAMA tự động biến mất (`do die`).
2. **Khớp số lượng tuyệt đối**:
   - Chỉ số **Xe thực tế (YOLO)** trên bảng HUD luôn bằng chính xác chỉ số **Tác tử số (GAMA)**.
3. **Cơ chế chống nghẽn ghi (Atomic Write)**:
   - Dữ liệu được trao đổi liên tục ở tần số cao (~15 - 25 FPS) mà không bao giờ xảy ra lỗi xung đột tập tin (`File In Use` hoặc JSON rỗng).
