# Kế Hoạch Triển Khai: Tinh Gọn Dự Án GAMA Digital Twin Cho 2 Thư Mục Báo Cáo

## 1. Mục Tiêu (Goal Description)
Theo yêu cầu của bạn, GAMA Platform quản lý và mở các mô hình theo chuẩn **GAMA Project** (yêu cầu thư mục chứa tệp cấu hình `.project`, `.settings/`, thư mục `models/` và tài nguyên `includes/`).
Hiện tại, cả 2 thư mục nghiệm thu cần có **thư mục dự án GAMA riêng biệt**, được **học tập và tinh gọn từ dự án gốc** `canntho_traffic_simulation` để:
1. Giám khảo có thể mở GAMA -> Import trực tiếp từng thư mục dự án một cách độc lập mà không bị xung đột tên hoặc lẫn lộn tệp Python.
2. **Kế thừa hình học không gian thực tế của nút giao thông Cần Thơ** (Đường 30/4 - Nguyễn Văn Linh) từ `canntho_traffic_simulation`.
3. **Tinh gọn tối đa**: Loại bỏ các tệp GIS khổng lồ không cần thiết (như `building.dbf` nặng tới 35MB), chỉ giữ lại các tệp cốt lõi (~1MB) giúp mô phỏng khởi động ngay lập tức (<1s), không tốn RAM và chạy mượt mà 60 FPS.

---

## 2. Kiến Trúc & Cấu Trúc Thư Mục
- Thư mục 1: `1_Digital_Twin_Vehicle_Detection/gama_vehicle_twin/` chứa mô hình `CanTho_Vehicle_Digital_Twin.gaml` và tài nguyên GIS Cần Thơ tinh gọn.
- Thư mục 2: `2_Digital_Twin_ROI_Pressure/gama_roi_pressure/` chứa mô hình `CanTho_ROI_Digital_Twin.gaml` và các vùng ROI `ROI_zones 2.shp`.
- Tự động phát hiện đường dẫn JSON linh hoạt (`../live_traffic.json` hoặc `../../live_traffic.json`).

---

## 3. Khắc Phục 2 Vấn Đề Đồng Bộ & Thu Gọn Không Gian Nút Giao (Status: DONE)
1. **Vấn đề 1: Đồng bộ dữ liệu Live YOLOv8 -> GAMA**:
   - *Nguyên nhân*: Lỗi `ParseException` do ép kiểu `map<string, unknown>(data["counts"])` khiến reflex `sync_from_yolo` bị ngắt trước khi cập nhật số lượng và sinh xe.
   - *Giải pháp*: Chuyển sang gán map trực tiếp (`map counts_map <- data["counts"];`), loại bỏ khối casting thừa. Dữ liệu nhận diện tức thì và cập nhật 1-1 với FPS camera.
2. **Vấn đề 2: Thu gọn bản đồ còn 1 ngã 4 duy nhất & sinh xe trên đường tiếp cận**:
   - *Giải pháp*:
     + Giới hạn kích thước không gian chuẩn 240m x 240m (tâm tại `{120, 120}`).
     + Vẽ đầy đủ vạch kẻ đường, vạch phân làn, vạch dừng đèn đỏ, vạch sang đường người đi bộ và 4 cụm đèn tín hiệu.
     + Nhánh Nam (South Approach): Xác định điểm xuất phát sinh xe tại `{125, 230}` và vạch dừng ngã tư tại `{125, 136}`.
     + Tọa độ chuẩn hóa `norm_x, norm_y` từ YOLOv8 ánh xạ trực tiếp lên nhánh đường này: xe sinh ra tại đầu đường tiếp cận và di chuyển mượt mà về phía ngã tư.

---

## 4. Dự Án GAMA Mới: Tích Hợp Bản Đồ GIS Thực Tế Nguyễn Văn Cừ - Nguyễn Văn Linh (Từ TrafficSi)
### 4.1 Mục tiêu
Tạo thêm 1 bản mô hình GAMA Digital Twin riêng biệt (`gama_trafficsi_twin`) song song với bản 3 làn hiện tại (`gama_vehicle_twin`), sử dụng bộ dữ liệu GIS thực tế từ `/Users/tonfud/Downloads/TrafficSi_/TrafficSi/includes`:
- Tuyến đường Nguyễn Văn Cừ & Nguyễn Văn Linh (`road.shp`, 12 phân đoạn, dual-carriageway).
- Tòa nhà không gian xung quanh (`building.shp`).
- Hệ thống đèn tín hiệu giao thông thực tế (`traffic_light.shp`).
- Đồng bộ dữ liệu Live Tracking thời gian thực từ YOLOv8 (`detect_and_sync.py`).

### 4.2 Thiết kế kiến trúc
- **Vị trí**: `1_Digital_Twin_Vehicle_Detection/gama_trafficsi_twin/`
- **Tài nguyên**:
  - `includes/`: Sao chép `road.*`, `building.*`, `traffic_light.*` từ `TrafficSi/includes`, tạo `road.shx` chuẩn GIS.
  - `models/CanTho_TrafficSi_Digital_Twin.gaml`: Mô hình GAMA độc lập kế thừa đầy đủ các bài học kinh nghiệm (Cổng kiểm tra trạng thái YOLO, chống xe nằm ngang, chống xe đi đè lên nhau, đồ họa xe đa lớp hiện đại, bảng HUD Telemetry).
- **Cơ chế đồng bộ**: `detect_and_sync.py` ghi atomic đồng thời ra cả `gama_vehicle_twin/live_traffic.json` và `gama_trafficsi_twin/live_traffic.json`.

### 4.3 Các bước triển khai (Status: HOÀN THÀNH 100%)
- [x] Bước 1: Khởi tạo cấu trúc dự án GAMA `gama_trafficsi_twin` (`.project`, `.settings/`, `includes/`, `models/`).
- [x] Bước 2: Sao chép toàn bộ Shapefiles từ `/Users/tonfud/Downloads/TrafficSi_/TrafficSi/includes` và chuẩn hóa `road.shx`.
- [x] Bước 3: Xây dựng mô hình `CanTho_TrafficSi_Digital_Twin.gaml` nạp hạ tầng đường, tòa nhà, đèn tín hiệu và mạng lưới driving graph.
- [x] Bước 4: Tích hợp đón xe từ camera YOLO trên nhánh tiếp cận Nguyễn Văn Cừ/Nguyễn Văn Linh.
- [x] Bước 5: Cập nhật `detect_and_sync.py` hỗ trợ phát đa điểm JSON (`gama_vehicle_twin` và `gama_trafficsi_twin`).
- [x] Bước 6: Biên dịch và kiểm thử qua `gama-headless.sh` (0 lỗi, nạp 12 roads, 290 buildings, 8 signals, 12 intersections).
