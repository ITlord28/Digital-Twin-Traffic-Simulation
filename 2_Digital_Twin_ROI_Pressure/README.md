# HƯỚNG DẪN KIỂM THỬ: DIGITAL TWIN ROI PRESSURE (MAX-PRESSURE & GAMA)

Thư mục này phục vụ kiểm chứng năng lực **Digital Twin (Bản sao số)** trong việc phân tích áp lực giao thông tiếp cận nút giao (ROI - Region of Interest) theo thuật toán **Max-Pressure** và phản chiếu trạng thái tắc nghẽn thời gian thực sang GAMA Simulation tại nút giao Cần Thơ.

---

## 1. Cấu Trúc Thành Phần
| Tệp / Thư mục | Chức năng kỹ thuật |
| :--- | :--- |
| **`calculate_roi_pressure.py`** | Script Python chạy YOLOv8 + ByteTrack tính toán 4 chỉ số khoa học: Bottom-Edge Grounding, Morphological Occupancy (Dilation 15x15), Queue Length (m), Max-Pressure Score. Xuất `roi_telemetry.json`. |
| **`get_coordinates.py`** | Công cụ nhấp chuột trực quan trên video/camera để lấy tọa độ đa giác ROI, xuất ra `roi_config.json`. |
| **`roi_config.json`** | File cấu hình lưu tọa độ các đỉnh đa giác ROI. |
| **`roi_telemetry.json`** | File dữ liệu cầu nối đo đạc áp lực thời gian thực bằng cơ chế Atomic Write. |
| **`yolov8n.pt`** | Trọng số mô hình YOLOv8 nạp sẵn (hỗ trợ tự nạp `yolov8s.pt` nếu có). |
| **`gama_roi_pressure_trafficsi/`** | **Dự án GAMA Digital Twin (Bản đồ GIS thực tế TrafficSi)**: Bản đồ GIS thực tế TrafficSi NVC–NVL (WGS84, tự reproject UTM 48N), 12 tuyến đường + 290 công trình, ROI 9m × 94m trên nhánh **SE – Nguyễn Văn Linh inbound** (cách nút giao 8m). Giao diện sáng, không hiển thị đèn tín hiệu, không sinh xe; HUD tự scale theo bản đồ; đọc telemetry trực tiếp tại `../roi_telemetry.json`. |

---

## 2. Các Bước Thực Hiện Kiểm Thử

### 🔹 Bước 1 (Tùy chọn): Lấy Tọa Độ Vùng ROI Mới
Nếu Hội đồng thử nghiệm với một video mới hoặc muốn xác định lại vùng ROI:
```bash
python get_coordinates.py
```
*(Hoặc `python3 get_coordinates.py`)*
- Chọn nguồn (phím `1` cho Video, phím `2` cho Camera).
- Nhấp **CHUỘT TRÁI** vào các góc giao lộ trên khung hình để tạo đa giác ROI.
- Nhấn phím `s` hoặc phím `q`: Chương trình tự động lưu cấu hình chuẩn vào `roi_config.json`.

---

### 🔹 Bước 2: Chạy Script Tính Áp Lực ROI (Python)
Mở Terminal tại thư mục này và chạy:
```bash
python calculate_roi_pressure.py
```
*(Hoặc `python3 calculate_roi_pressure.py`)*

Hệ thống sẽ hỏi chọn nguồn dữ liệu:
- Nhấn `1`: Video thực nghiệm ROI có sẵn (`intersection_1_roi.mp4`).
- Nhấn `2`: Live Camera / Webcam máy tính (Camera 0).

*(Hoặc chạy lệnh chỉ định trực tiếp: `python calculate_roi_pressure.py --source 1` hoặc `--source 2`).*

**Phím tắt điều khiển đặc biệt**:
- `m`: **Chuyển đổi qua lại giữa xem Video thường và xem Mặt Nạ Hình Thái Học (Morphological Mask)** để kiểm chứng thuật toán Dilation gộp cụm xe.
- `p` hoặc phím `Space`: Tạm dừng / Tiếp tục video.
- `s`: Lưu ảnh chụp minh chứng.
- `q`: Thoát chương trình.

---

### 🔹 Bước 3: Khởi Động Dự Án GAMA Platform
1. Khởi động ứng dụng **GAMA Platform**.
2. Thao tác nạp dự án:
   - Chọn menu **File -> Import...** -> **General -> Existing Projects into Workspace** -> **Next**.
   - Tại **Select root directory**, trỏ tới thư mục dự án:
     `2_Digital_Twin_ROI_Pressure/gama_roi_pressure_trafficsi`
   - Bấm **Finish**. Dự án `CanTho_ROI_TrafficSi_DigitalTwin` sẽ xuất hiện trong Navigator.
3. Trong Navigator, mở `models/` và mở tệp:
   `CanTho_ROI_TrafficSi_Digital_Twin.gaml` → chạy **CanThoROITrafficSiExperiment**.
4. Bấm nút màu xanh trên thanh công cụ để chạy mô phỏng.

> **Nếu vừa khôi phục file GAML từ local history:** đóng tab model đang mở và mở lại từ đĩa trước khi chạy; không bấm Save trên buffer cũ vì buffer đó có thể không còn khối HUD.

> **Lưu ý CRS:** `gama_roi_pressure_trafficsi/includes/` giữ nguyên shapefile WGS84. GAMA 2025.6.4 tự động reproject sang UTM 48N (EPSG:32648) theo preference mặc định, nên ROI 9m × 94m và chiều rộng đường 14m giữ đúng đơn vị mét; không cần chạy `ogr2ogr`. Bản sao `road.shp` được bổ sung `road.shx` (nguồn TrafficSi gốc thiếu file index) để GeoTools đọc ổn định.

---

## 3. Tiêu Chí Đánh Giá Tính Năng Digital Twin
1. **Phản chiếu biến động tắc nghẽn thời gian thực (Congestion Mirroring)**:
   - Khi dòng xe dồn ứ trước vạch dừng trên video $\rightarrow$ Vùng ROI trên GAMA lập tức chuyển từ **Xanh lá (Thông thoáng)** sang **Vàng cam (Đông đúc)** và **Đỏ đậm (Ùn tắc)**.
2. **Khớp nối chỉ số khoa học tuyệt đối**:
   - Chỉ số Mật độ chiếm dụng hình thái học (**Occupancy %**), Chiều dài hàng đợi (**Queue Length**), và Áp lực (**Max-Pressure**) trên HUD của Python khớp 100% với các thông số hiển thị trên HUD GAMA.
3. **Cơ sở cho thuật toán điều khiển đèn giao thông thích ứng**:
   - Áp lực được tính toán bằng phương pháp Max-Pressure thực địa $Pressure = Occupancy \times Queue\_Length$ chính là giá trị đầu vào cho chu kỳ pha đèn xanh trong điều khiển giao thông thông minh.
4. **Heartbeat kết nối thời gian thực**:
   - GAMA chỉ hiển thị **LIVE** khi `timestamp` trong telemetry mới hơn **2 giây**. Nếu Python dừng hoặc video bị tạm dừng quá 2 giây, HUD chuyển **MẤT KẾT NỐI** và vùng ROI chuyển xám để tránh hiển thị dữ liệu cũ như dữ liệu sống.
5. **Đồng bộ giao diện với mô hình Vehicle Detection (bản sơ đồ 240m)**:
   - Nền sáng (light mode), vạch phân làn 3 làn/chiều, không hiển thị đèn tín hiệu giao thông; HUD dùng card trắng viền xanh nhạt đồng bộ với mô hình 1.
6. **Bản đồ TrafficSi thực tế (bản thứ hai)**:
   - Nạp đúng 12 tuyến đường + 290 công trình từ TrafficSi; ROI 9m × 94m nằm trên nhánh SE – Nguyễn Văn Linh inbound, cách nút giao 8m; HUD tự co giãn theo bản đồ ~504m × 465m để chữ 9–11px không tràn.
   - Không hiển thị 8 điểm đèn tín hiệu và không sinh xe; ROI đổi màu theo `status_code`, thanh hàng chờ và nhãn ROI hiển thị đúng phía nhánh SE.
