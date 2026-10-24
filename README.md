# HỆ THỐNG BẢN SAO SỐ GIAO THÔNG ĐÔ THỊ (DIGITAL TWIN TRAFFIC SIMULATION)
### YOLOv8 Computer Vision & GAMA Agent-Based Platform (Nút Giao Nguyễn Văn Cừ – Nguyễn Văn Linh, Cần Thơ)

---

> [!IMPORTANT]
> ### ⚖️ TUYÊN BỐ BẢN QUYỀN, MỤC ĐÍCH SỬ DỤNG & MIỄN TRỪ TRÁCH NHIỆM PHÁP LÝ
> 1. **Mục đích phục vụ công tác Nghiên cứu Khoa học (NCKH):**
>    Toàn bộ mã nguồn, cấu hình mô phỏng, thuật toán và dữ liệu trong kho lưu trữ này được xây dựng và chia sẻ **duy nhất nhằm phục vụ công tác nghiên cứu khoa học, học thuật và giáo dục** trong lĩnh vực Thị giác máy tính (Computer Vision), Hệ thống Giao thông Thông minh (Intelligent Transportation Systems - ITS) và Mô phỏng Bản sao số (Digital Twin).
> 2. **Phi thương mại (Non-Commercial):**
>    Mã nguồn hoàn toàn phi thương mại. Nghiêm cấm mọi hình thức thương mại hóa, mua bán, chuyển giao có thu phí hoặc sử dụng vào mục đích kinh doanh, sinh lợi khi chưa có văn bản chấp thuận chính thức từ tác giả.
> 3. **Miễn trừ hoàn toàn trách nhiệm pháp lý (Disclaimer of Liability):**
>    Toàn bộ đoạn mã và mô hình được cung cấp theo nguyên tắc **"NGUYÊN TRẠNG" (AS-IS)** mà không có bất kỳ cam kết hay bảo đảm nào (dù minh thị hay ngụ ý). Tác giả và nhóm nghiên cứu **KHÔNG CHỊU BẤT KỲ TRÁCH NHIỆM PHÁP LÝ NÀO** đối với bất kỳ khiếu nại, tranh chấp, thiệt hại trực tiếp, gián tiếp hoặc hậu quả phát sinh từ việc cài đặt, thực thi, sửa đổi, vận hành hoặc phụ thuộc vào đoạn mã nguồn này. Người sử dụng tự chịu mọi trách nhiệm khi khai thác hệ thống.

---

## 📌 Giới Thiệu Dự Án

Dự án hiện thực hóa kiến trúc **Bản sao số (Digital Twin)** hai chiều cho mạng lưới giao thông đô thị Việt Nam:
1. **Lớp Giám sát Thực tế (Physical Layer / Computer Vision)**:
   - Ứng dụng **YOLOv8 + ByteTrack** để phát hiện, theo dõi và phân loại đa phương tiện giao thông đặc thù Việt Nam (ô tô con, xe máy, xe buýt, xe tải).
   - Đo đạc các chỉ số giao thông tiên tiến: Mật độ hình thái học (**Morphological Occupancy Dilation 15x15**), Chiều dài hàng đợi xe (**Queue Length theo mét**), và Áp lực tiếp cận nút giao (**Max-Pressure**).
2. **Lớp Bản sao số Mô phỏng (Cyber-Twin Layer / GAMA Platform)**:
   - Tái tạo không gian giao thông thực tế dựa trên tập dữ liệu GIS **TrafficSi** tại nút giao trọng điểm **Nguyễn Văn Cừ – Nguyễn Văn Linh (TP. Cần Thơ)**: 12 tuyến đường đa làn, 290 công trình kiến trúc, phân làn chuẩn và tọa độ WGS84 chuyển đổi tự động sang UTM 48N.
   - Giao tiếp dữ liệu thời gian thực thông qua cơ chế ghi chống xung đột **Atomic Write (JSON IPC)** với tần số phản hồi cao (15–25 FPS).

---

## 🗂 Cấu Trúc Kho Lưu Trữ

Kho lưu trữ gồm 2 phân hệ Digital Twin độc lập, hoàn chỉnh:

```text
practiceYolo8/
├── 1_Digital_Twin_Vehicle_Detection/      # [MODULE 1] ĐỒNG BỘ TÁC TỬ XE LIVE (1-1)
│   ├── detect_and_sync.py                 # Script Python: YOLOv8 tracking & xuất live_traffic.json
│   ├── live_traffic.json                  # Kênh dữ liệu đồng bộ trạng thái phương tiện thời gian thực
│   ├── gama_trafficsi_twin/               # Dự án GAMA độc lập (Bản đồ GIS TrafficSi Cần Thơ)
│   │   ├── .project, .settings/           # Cấu hình dự án Eclipse / GAMA
│   │   ├── includes/                      # Dữ liệu GIS: road (shp, shx, dbf, prj), building, traffic_light
│   │   └── models/
│   │       └── CanTho_TrafficSi_Digital_Twin.gaml # Mô hình Digital Twin tác tử xe tự hành
│   └── README.md                          # Hướng dẫn chi tiết chạy Module 1
│
├── 2_Digital_Twin_ROI_Pressure/           # [MODULE 2] ĐỒNG BỘ ÁP LỰC ROI & MAX-PRESSURE
│   ├── calculate_roi_pressure.py          # Script Python: Tính Occupancy, Queue Length, Max-Pressure
│   ├── get_coordinates.py                 # Công cụ nhấp chuột xác định vùng quan tâm ROI trực quan
│   ├── roi_config.json                    # Cấu hình tọa độ đỉnh vùng ROI
│   ├── roi_telemetry.json                 # Kênh dữ liệu đo đạc áp lực giao thông thời gian thực
│   ├── gama_roi_pressure_trafficsi/       # Dự án GAMA độc lập (Bản đồ GIS TrafficSi Cần Thơ)
│   │   ├── .project, .settings/           # Cấu hình dự án Eclipse / GAMA
│   │   ├── includes/                      # Dữ liệu GIS nút giao Cần Thơ (WGS84 -> UTM 48N)
│   │   └── models/
│   │       └── CanTho_ROI_TrafficSi_Digital_Twin.gaml # Mô hình Digital Twin vùng áp lực ROI
│   └── README.md                          # Hướng dẫn chi tiết chạy Module 2
│
├── .gitignore                             # Loại bỏ môi trường ảo, cache và video dung lượng lớn
├── LICENSE                                # Giấy phép CC BY-NC 4.0 & Điều khoản miễn trừ trách nhiệm
└── README.md                              # Tài liệu tổng quan dự án
```

---

## 🚀 Hướng Dẫn Vận Hành Nhanh

### 1. Chuẩn Bị Môi Trường Python
```bash
# Cài đặt các thư viện cần thiết
pip install ultralytics opencv-python numpy shapely
```

### 2. Chạy Module 1: Đồng Bộ Tác Tử Xe Live (Vehicle Twin)
1. **Khởi động Python Detector**:
   ```bash
   cd 1_Digital_Twin_Vehicle_Detection
   python detect_and_sync.py
   # Chọn 1 (Video) hoặc 2 (Live Webcam/Camera)
   ```
2. **Khởi động GAMA**:
   - Mở GAMA Platform $\rightarrow$ **File -> Import... -> Existing Projects into Workspace**.
   - Chọn thư mục `1_Digital_Twin_Vehicle_Detection/gama_trafficsi_twin`.
   - Mở file `models/CanTho_TrafficSi_Digital_Twin.gaml` $\rightarrow$ Nhấn **CanThoTrafficSiExperiment**.

### 3. Chạy Module 2: Đồng Bộ Áp Lực Vùng ROI (Pressure Twin)
1. **Khởi động Python Calculator**:
   ```bash
   cd 2_Digital_Twin_ROI_Pressure
   python calculate_roi_pressure.py
   # Chọn 1 (Video) hoặc 2 (Live Webcam/Camera)
   ```
2. **Khởi động GAMA**:
   - Mở GAMA Platform $\rightarrow$ Import thư mục `2_Digital_Twin_ROI_Pressure/gama_roi_pressure_trafficsi`.
   - Mở file `models/CanTho_ROI_TrafficSi_Digital_Twin.gaml` $\rightarrow$ Nhấn **CanThoROITrafficSiExperiment**.

---

## 📊 Điểm Nổi Bật Về Mặt Khoa Học & Kỹ Thuật

- **Đồng bộ thực thể 1-1 không nghẽn kênh**: Đảm bảo mỗi phương tiện vật lý được ánh xạ thành một tác tử số có thuộc tính hình học và vận tốc chính xác.
- **Tính toán Max-Pressure thực địa**: Ứng dụng tích hình thái học $Pressure = Occupancy \times Queue\_Length$ làm cơ sở tối ưu hóa chu kỳ đèn tín hiệu giao thông thông minh thích ứng.
- **Tự động chuyển đổi hệ tọa độ (CRS)**: Tự động chiếu từ WGS84 sang UTM 48N (EPSG:32648) tại Cần Thơ, đảm bảo tỷ lệ khoảng cách, chiều rộng làn đường (14m) và vùng quan sát (9m × 94m) chính xác theo đơn vị mét.
- **Kiến trúc bền vững (Fault-Tolerant)**: Cơ chế Heartbeat 2 giây tự động nhận diện ngắt kết nối hoặc tạm dừng luồng camera, tránh hiển thị sai lệch thông số thực tế.

---

## 📜 Bản Quyền & Giấy Phép
Dự án được bảo hộ theo giấy phép **Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)**.
Vui lòng đọc kỹ tập tin [`LICENSE`](file:///Users/tonfud/Documents/HocTap_NCKH/NCKH/practiceYolo8/LICENSE) trước khi sử dụng.
Mọi thắc mắc học thuật xin liên hệ tác giả qua GitHub: [@ITLord28](https://github.com/ITLord28).
