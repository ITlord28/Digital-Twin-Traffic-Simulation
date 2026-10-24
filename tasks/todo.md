# Danh Sách Công Việc (Todo List) - Tinh Gọn 2 GAMA Project Độc Lập

## Giai đoạn 1: Tinh Gọn GAMA Project Thư Mục 1 (`1_Digital_Twin_Vehicle_Detection/gama_vehicle_twin/`)
- [x] 1.1 Khởi tạo cấu trúc thư mục `1_Digital_Twin_Vehicle_Detection/gama_vehicle_twin/` với `.project`, `.settings/`, `includes/`, `models/`
- [x] 1.2 Sao chép tài nguyên GIS tinh gọn từ `canntho_traffic_simulation` (`road 4.*`, `bg1.png`, tổng ~800KB, loại bỏ `building.dbf`)
- [x] 1.3 Xây dựng mô hình `CanTho_Vehicle_Digital_Twin.gaml`:
  - [x] Nạp bản đồ vệ tinh Cần Thơ (`bg1.png`) và tim đường GIS (`road 4.shp`)
  - [x] Đọc live `live_traffic.json` linh hoạt (`../live_traffic.json` hoặc `../../live_traffic.json`)
  - [x] Tự động sinh xe Digital Twin, cập nhật tọa độ chuẩn hóa và hủy tác tử khi rời camera
  - [x] Bảng HUD kết nối Live Sync & biểu đồ số lượng phương tiện
- [x] 1.4 Cập nhật `README.md` của Thư mục 1: Hướng dẫn giám khảo import dự án `gama_vehicle_twin` vào GAMA

## Giai đoạn 2: Tinh Gọn GAMA Project Thư Mục 2 (`2_Digital_Twin_ROI_Pressure/gama_roi_pressure/`)
- [x] 2.1 Khởi tạo cấu trúc thư mục `2_Digital_Twin_ROI_Pressure/gama_roi_pressure/` với `.project`, `.settings/`, `includes/`, `models/`
- [x] 2.2 Sao chép tài nguyên GIS tinh gọn (`road 4.*`, `ROI_zones 2.*`, `traffic_signals 8.*`, `bg1.png`, tổng ~1MB)
- [x] 2.3 Xây dựng mô hình `CanTho_ROI_Digital_Twin.gaml`:
  - [x] Nạp nền đường, đèn tín hiệu và các đa giác ROI (`ROI_zones 2.shp`)
  - [x] Đọc live `roi_telemetry.json` do Python xuất ra
  - [x] Đổi màu đa giác ROI động theo chỉ số Max-Pressure (Xanh lá -> Vàng cam -> Đỏ cảnh báo)
  - [x] Thước đo chiều dài hàng đợi Queue Length theo mét và đồ thị Max-Pressure theo thời gian
- [x] 2.4 Cập nhật `README.md` của Thư mục 2: Hướng dẫn giám khảo import dự án `gama_roi_pressure` vào GAMA

## Giai đoạn 3: Kiểm Thử & Nghiệm Thu
- [x] 3.1 Dọn dẹp tệp cấu hình `.project` cũ ở thư mục cha để tránh lẫn lộn
- [x] 3.2 Kiểm thử chạy Python và kiểm tra độ tương thích của 2 GAMA project
- [x] 3.3 Cập nhật `tasks/changelog.html` và báo cáo hoàn thành

## Giai đoạn 4: Sửa Đồng Bộ Live YOLO -> GAMA & Thu Gọn Bản Đồ Về 1 Ngã Tư Duy Nhất
- [x] 4.1 Khắc phục lỗi ép kiểu Map GAML (`ParseException: Expected value at 1:1`) trong cả 2 file GAML
- [x] 4.2 Tái thiết kế không gian GAMA tập trung 1 ngã tư 4 chiều duy nhất (240m x 240m) thay cho bản đồ toàn thành phố 5km x 5km
- [x] 4.3 Ánh xạ điểm sinh xe trực tiếp trên nhánh tiếp cận phía Nam (South Approach: điểm xuất phát `y=230m` tiến dần về vạch dừng ngã tư `y=136m`)
- [x] 4.4 Đồng bộ Folder 2 (`CanTho_ROI_Digital_Twin.gaml`) với vùng quan tâm ROI nằm trên nhánh tiếp cận ngã tư
- [x] 4.5 Xác minh biên dịch độc lập qua `gama-headless.sh` (100% pass)

## Giai đoạn 5: Tinh Chỉnh Thư Mục 1 - Sinh Xe Tự Hành Ngẫu Nhiên & Tone Màu Sáng
- [x] 5.1 Xây dựng bộ điều khiển phát hiện xe mới từ YOLO (`spawned_ids`) và sinh xe tại 1 điểm đón `{125.0, 230.0}`
- [x] 5.2 Lập trình hành vi di chuyển tự hành ngẫu nhiên `skills: [moving]` qua ngã tư (Đi thẳng 60%, Rẽ phải 20%, Rẽ trái 20%)
- [x] 5.3 Thiết lập cơ chế xoay thân xe theo góc lái `heading` và vòng đời tồn tại `lifespan <- 350;` tự giải phóng
- [x] 5.4 Gỡ bỏ hoàn toàn đèn tín hiệu giao thông tại ngã tư
- [x] 5.5 Chuyển đổi toàn diện giao diện sang Tone Màu Sáng (Light Theme: nền `#f8fafc`, lòng đường xám sáng, HUD Glassmorphism trắng)
- [x] 5.6 Xác minh biên dịch độc lập và chạy thử nghiệm GAMA Headless (100% PASS)

## Giai đoạn 6: Sửa Triệt Để Lỗi Đùn Ứ, Chống Trùng Lặp & Tinh Giản Tag
- [x] 6.1 Khắc phục lỗi nhân đôi `step` trong `do goto speed:` giúp xe di chuyển đúng tốc độ thực (12 m/s)
- [x] 6.2 Loại bỏ logic reset `spawned_ids` trên timestamp, đảm bảo 1 xe video chỉ sinh đúng 1 xe trong GAMA
- [x] 6.3 Tăng `lifespan <- 800;` để xe thoải mái vượt qua ngã tư sang các nhánh Bắc, Đông, Tây
- [x] 6.4 Tinh giản nhãn hiển thị chỉ còn tên loài xe (`v_class`), loại bỏ hoàn toàn ID và text rườm rà
- [x] 6.5 Xác minh biên dịch headless PASS 100%




## Giai đoạn 7: Nâng Cấp Giao Lộ 3 Làn Từ Shapefile `road.shp` & Đồ Họa Chuẩn VISSIM/SUMO
- [x] 7.1 Tạo Shapefile `1_Digital_Twin_Vehicle_Detection/gama_vehicle_twin/includes/road.shp` (3 làn mỗi chiều, rộng 36m, 11 phân đoạn kết nối ngã tư)
- [x] 7.2 Cập nhật `CanTho_Vehicle_Digital_Twin.gaml` nạp hạ tầng trực tiếp từ `road_shp <- shape_file("../includes/road.shp")`
- [x] 7.3 Phân làn xe tự nhiên theo chuẩn Việt Nam (Làn 1: Ô tô nhanh, Làn 2: Hỗn hợp/Xe buýt/Xe tải, Làn 3: Xe máy sát lề)
- [x] 7.4 Lựa chọn lộ trình ngẫu nhiên dọc theo mạng lưới đường từ road.shp (Đi thẳng 60%, Rẽ phải 20%, Rẽ trái 20%)
- [x] 7.5 Nâng cấp đồ họa tác tử xe chuẩn VISSIM/SUMO: Thân xe bo góc, kính chắn gió sẫm màu, dải đèn pha trước vàng sáng
- [x] 7.6 Xóa bỏ hoàn toàn text tag trên xe để tầm nhìn thông thoáng; gom trạng thái live vào bảng HUD Glassmorphism
- [x] 7.7 Tương thích 100% cấu trúc JSON giữa Python và GAMA parser (`class`, `source_name`, `counts["total"]`)
- [x] 7.8 Xác minh biên dịch độc lập qua `gama-headless.sh` (100% PASS)

## Giai đoạn 8: Khắc Phục Lỗi Gãy Kết Nối Do Kẹt Cache ID Khi Khởi Động Lại YOLO
- [x] 8.1 Thêm cơ chế bắt tay `session_id` trong Python `detect_and_sync.py`
- [x] 8.2 Lập trình GAMA tự động phát hiện phiên làm việc mới để xóa xe cũ và đón xe ngay lập tức
- [x] 8.3 Thêm bộ giám sát video lặp chu kỳ tự làm mới `spawned_ids`
- [x] 8.4 Kiểm tra động qua `active_ids` và xoay vòng buffer sau 150 xe
- [x] 8.5 Thêm thông báo console log `🚗 [SINH XE LIVE]` khi xe xuất hiện
- [x] 8.6 Đồng bộ song song cả 2 file `CanTho_Vehicle_Digital_Twin.gaml` và `Vehicle_Digital_Twin.gaml`
- [x] 8.7 Kiểm thử liên tục 1000 bước chạy với YOLO, xác nhận 14/14 xe sinh thành công tức thì

## Giai đoạn 9: Sửa Hướng Xoay Xe Dọc Đường & Chống Xe Đi Chồng Lên Nhau
- [x] 9.1 Sửa hướng vẽ hình học `rectangle(v_length, v_width) rotated_by heading` chuẩn chiều dài dọc đường
- [x] 9.2 Khởi tạo `heading <- 270.0` (hướng Bắc dọc đường)
- [x] 9.3 Tọa độ đèn pha trước tại cản trước và đèn hậu tại cản sau theo góc `heading`
- [x] 9.4 Dàn trải vị trí sinh `spawn_y` theo `cam_norm_y` từ camera và kiểm tra an toàn chống sinh đè
- [x] 9.5 Thêm mô hình bám đuôi an toàn Car-Following: giảm tốc/dừng khi có xe phía trước cùng làn
- [x] 9.6 Đồng bộ song song cả 2 file `CanTho_Vehicle_Digital_Twin.gaml` và `Vehicle_Digital_Twin.gaml`
- [x] 9.7 Xác minh biên dịch headless cả 2 file đạt 100% PASS

## Giai đoạn 10: Khắc Phục Xe Xuất Hiện Khi Chưa Bật YOLO & Hoàn Thiện Hướng Xoay Phương Tiện
- [x] 10.1 Thêm cổng kiểm tra trạng thái YOLO (`status = "running"`) trong GAMA: không sinh xe khi YOLO chưa bật hoặc đã dừng
- [x] 10.2 Khởi tạo và reset cả 2 file `live_traffic.json` về trạng thái `stopped` sạch sẽ khi bắt đầu
- [x] 10.3 Bọc khối `try...finally` trong Python `detect_and_sync.py` để đảm bảo luôn ghi `stopped` khi thoát chương trình
- [x] 10.4 Khắc phục lỗi gán `location` làm ghi đè `heading` trong GAMA: gán vị trí trước, gán `heading <- 270.0;` sau
- [x] 10.5 Cập nhật liên tục `heading` theo waypoint mục tiêu trong `reflex navigate` ngay cả khi xe đang dừng phanh
- [x] 10.6 Tính toán góc vẽ độc lập `draw_angle` theo waypoint trong `aspect default`
- [x] 10.7 Hoàn thiện đồ họa xe đa lớp: Chassis bo viền, kính chắn gió/cabin tối màu, nóc xe sáng bóng, dải đèn LED pha vàng trước và đèn hậu đỏ sau
- [x] 10.8 Đồng bộ 100% giữa 2 file `CanTho_Vehicle_Digital_Twin.gaml` và `Vehicle_Digital_Twin.gaml`
- [x] 10.9 Xác minh biên dịch độc lập qua `gama-headless.sh` (0 lỗi, 100% PASS)

## Giai đoạn 11: Tạo Bản Digital Twin Mới Dùng Bản Đồ TrafficSi (Nguyễn Văn Cừ - Nguyễn Văn Linh)
- [x] 11.1 Khởi tạo thư mục dự án GAMA `1_Digital_Twin_Vehicle_Detection/gama_trafficsi_twin/` với cấu trúc `.project`, `.settings/`, `includes/`, `models/`
- [x] 11.2 Sao chép tài nguyên GIS `road.*`, `building.*`, `traffic_light.*` từ `/Users/tonfud/Downloads/TrafficSi_/TrafficSi/includes` và tạo `road.shx`
- [x] 11.3 Xây dựng mô hình `CanTho_TrafficSi_Digital_Twin.gaml`:
  - [x] Nạp Shapefile `road.shp`, `building.shp`, `traffic_light.shp`
  - [x] Tạo mạng lưới giao thông `as_driving_graph(road, intersection)`
  - [x] Kết nối `live_traffic.json`, kiểm tra cổng `status == "running"`
  - [x] Thiết lập điểm đón xe camera tại nhánh tiếp cận đường Nguyễn Văn Cừ / Nguyễn Văn Linh
  - [x] Điều hướng xe tự hành, bám đuôi an toàn, không chồng xác
  - [x] Đồ họa xe đa lớp hiện đại và bảng HUD Telemetry Cần Thơ Digital Twin
- [x] 11.4 Cập nhật `detect_and_sync.py` ghi đồng thời ra cả `gama_trafficsi_twin/live_traffic.json`
- [x] 11.5 Biên dịch và kiểm thử qua `gama-headless.sh` (0 lỗi, 100% PASS)
- [x] 11.6 Cập nhật `tasks/changelog.html` và hướng dẫn người dùng

## Giai đoạn 12: Sửa Lỗi Thụt Lề (IndentationError) Trong Python detect_and_sync.py
- [x] 12.1 Tái cấu trúc logic tạm dừng `is_paused` theo mẫu Guard Clause ở đầu vòng lặp `while True:`
- [x] 12.2 Đảm bảo thụt lề chuẩn cho toàn bộ khối mã đọc video và tracking YOLO
- [x] 12.3 Kiểm tra cú pháp bằng `python -m py_compile detect_and_sync.py` (0 lỗi, 100% PASS)
- [x] 12.4 Cập nhật bài học kinh nghiệm trong `tasks/lessons.md`

## Giai đoạn 13: Kiểm Tra & Tối Ưu Kết Nối Digital Twin Giữa calculate_roi_pressure.py Và gama_roi_pressure_trafficsi
- [x] 13.1 Mở rộng `JSON_TELEMETRY_PATHS` trong Python để ghi atomic trực tiếp vào `gama_roi_pressure_trafficsi/roi_telemetry.json`
- [x] 13.2 Khởi tạo tệp `gama_roi_pressure_trafficsi/roi_telemetry.json` sẵn sàng cho GAMA nạp ngay tức thì
- [x] 13.3 Cập nhật `telemetry_path` trong GAML với cơ chế fallback thông minh: ưu tiên đường dẫn nội bộ an toàn `../roi_telemetry.json`, dự phòng `../../roi_telemetry.json`
- [x] 13.4 Chạy kiểm thử mô phỏng Batch qua `gama-headless.sh`: Tải 12 tuyến đường, 290 công trình, tạo ROI 94m x 9m trên nhánh SE Nguyễn Văn Linh và đồng bộ telemetry thành công 100%
- [x] 13.5 Cập nhật tài liệu hướng dẫn và báo cáo kết quả chi tiết

## Giai đoạn 14: Khắc Phục Triệt Để Lỗi Không Nhận Dữ Liệu Trong GAMA GUI
- [x] 14.1 Phân tích lỗi từ Screenshot người dùng: GAMA GUI hiển thị `Telemetry JSON : ../../roi_telemetry.json` và bị chặn bởi Eclipse Resource Manager
- [x] 14.2 Đổi `telemetry_path` trong `CanTho_ROI_TrafficSi_Digital_Twin.gaml` thành đường dẫn nội bộ cố định `../roi_telemetry.json`
- [x] 14.3 Thêm kiểm tra `contains_key` an toàn cho toàn bộ 10 trường dữ liệu JSON
- [x] 14.4 Bổ sung `chmod 644` trong Python atomic write để đảm bảo quyền đọc
- [x] 14.5 Cập nhật `tasks/lessons.md` với Bài học 12
- [x] 14.6 Hướng dẫn chi tiết thao tác đóng tab và F5 Refresh trong GAMA để nạp mã nguồn mới

## Giai đoạn 15: Tinh Gọn Folder 1 & Folder 2 Chỉ Giữ Bản Bản Đồ TrafficSi Chuẩn Bị Git Push
- [x] 15.1 Dọn dẹp thư mục 1: Xóa các file thừa `includes/`, `models/`, `.metadata/`, `.cache/`, `.built_in_models*`
- [x] 15.2 Cập nhật `detect_and_sync.py`: Tinh gọn `JSON_OUTPUT_FILES` chỉ xuất trực tiếp ra `live_traffic.json` và `gama_trafficsi_twin/live_traffic.json`
- [x] 15.3 Dọn dẹp thư mục 2: Xóa `gama_roi_pressure/`, `.workspace0/`, `tasks/`, các ảnh chụp màn hình tạm
- [x] 15.4 Cập nhật `calculate_roi_pressure.py`: Tinh gọn `JSON_TELEMETRY_PATHS` chỉ xuất trực tiếp ra `roi_telemetry.json` và `gama_roi_pressure_trafficsi/roi_telemetry.json`
- [x] 15.5 Cập nhật `README.md` ở cả 2 thư mục đồng bộ duy nhất với phiên bản TrafficSi
- [x] 15.6 Cập nhật `.gitignore` loại bỏ các file rác môi trường ảo, cache và metadata
- [x] 15.7 Biên dịch headless xác nhận cả 2 mô hình GAMA đạt PASS 100%
