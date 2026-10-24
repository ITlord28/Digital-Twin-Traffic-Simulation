# Bài Học Kinh Nghiệm (Lessons Learned)

## 1. Virtual Environment Mismatch & Broken Paths
- **Vấn đề**: Khi di chuyển dự án (từ `/Users/tonfud/Desktop/...` sang `/Users/tonfud/Documents/HocTap_NCKH/...`), môi trường ảo `venv` cũ bị hỏng đường dẫn shebang (`bad interpreter`) và thiếu các gói như `cv2`. Khi IDE tự động chọn `./venv/bin/python`, lệnh chạy bị lỗi `ModuleNotFoundError: No module named 'cv2'`.
- **Giải pháp**:
  - Tạo lại `venv` với cờ `--system-site-packages` để tái sử dụng toàn bộ thư viện tối ưu hóa trên máy (`opencv-python`, `ultralytics`, `torch`).
  - Hướng dẫn người dùng và giám khảo có thể chạy trực tiếp bằng `python3` hoặc `python`.

## 2. GAMA Eclipse Workspace Path Resolution Boundary (`IllegalArgumentException`)
- **Vấn đề**: Khi viết đường dẫn tương đối trong mô hình GAML có dạng `../../live_traffic.json` để vươn ra ngoài thư mục dự án GAMA, Eclipse Workspace Resource Manager ném lỗi:
  `IllegalArgumentException: Path must include project and resource name: /live_traffic.json` do vi phạm ranh giới quản lý tài nguyên của dự án Eclipse.
- **Giải pháp**:
  - Không bao giờ dùng `../../` để vượt ra ngoài ranh giới GAMA project.
  - Đặt file JSON ngay trong thư mục gốc của GAMA project (`gama_vehicle_twin/live_traffic.json` và `gama_roi_pressure/roi_telemetry.json`).
  - Đường dẫn trong GAML viết chuẩn nội bộ: `string json_path <- "../live_traffic.json";`.
  - Script Python (`detect_and_sync.py` & `calculate_roi_pressure.py`) được cấu hình ghi đồng thời ra cả thư mục cha và thư mục dự án GAMA để luôn đồng bộ tức thì.

## 3. Tính Nhất Quán Khi Refactor Biến Đường Dẫn
- **Vấn đề**: Khi đổi tên `JSON_OUTPUT_FILE` thành danh sách `JSON_OUTPUT_FILES`, một câu lệnh `print` cũ chưa được cập nhật dẫn đến lỗi `NameError`.
- **Giải pháp**: Luôn giữ bí danh tương thích ngược `JSON_OUTPUT_FILE = JSON_OUTPUT_FILES[0]` để bảo vệ toàn bộ các vị trí tham chiếu khác.

## 4. GAML Map Casting Bug Khi Đọc JSON (`ParseException: Expected value at 1:1`)
- **Vấn đề**: Khi đọc tệp JSON trong GAMA bằng `live_file <- json_file(path);`, thuộc tính `live_file.contents` đã trả về đối tượng `map` nguyên bản của GAMA. Nếu viết ép kiểu tham số `map<string, unknown>(data["counts"])`, toán tử ép kiểu của GAMA sẽ gọi `toString()` (tạo ra chuỗi cú pháp GAML `map(['total'::7,...])`) và chuyển vào `Json.parse()`, dẫn tới ngoại lệ `ParseException: Expected value at 1:1`. Ngoại lệ này bị khối `try...catch` nuốt trọn khiến reflex dừng giữa chừng, không cập nhật số liệu và không tạo tác tử xe (`is_connected` vẫn là `false`).
- **Giải pháp**:
  - Không dùng ép kiểu tham số `map<string, unknown>(...)` trên đối tượng map con.
  - Sử dụng gán trực tiếp: `map counts_map <- data["counts"];` hoặc truy xuất `data["counts"]["total"]`.
  - Giữ ranh giới không gian mô phỏng tập trung 240m x 240m tại 1 ngã 4 duy nhất để quan sát rõ nét 100% từng phương tiện và vùng tiếp cận camera.

## 5. Quy Chuẩn Cú Pháp GAML Trong Tác Tử Tự Hành (Skills Moving & Geometry)
- **Vấn đề**:
  - Viết `shape contains location` bên trong `species vehicle`: biến `shape` bị hiểu là hình dạng của chính chiếc xe, dẫn đến lỗi biên dịch.
  - Viết `remove first(list) from: list`: GAML yêu cầu chỉ định rõ ràng `remove index: 0 from: list;`.
  - Viết `draw rect rotate: heading`: GAML dùng toán tử hình học `draw (rect rotated_by heading) ...`.
- **Giải pháp**:
  - Kiểm tra biên thoát khỏi bản đồ bằng tọa độ: `location.x < -10.0 or location.x > 250.0 or location.y < -10.0 or location.y > 250.0`.
  - Dùng `waypoints[0]` và `remove index: 0 from: waypoints;` để điều hướng waypoint tuần tự.
  - Dùng `(rectangle(h, w) rotated_by heading)` để xoay thân xe mượt mà theo hướng bẻ lái.

## 6. Lỗi Nhân Đôi `step` Trong Toán Tử `goto` Của GAML & Chống Đùn Tác Tử
- **Vấn đề**: Trong skill `moving` của GAMA, toán tử `do goto target: ... speed: val;` đã **tự động nhân `val` với `step` ở tầng kernel**. Nếu lập trình viên truyền `speed: speed_val * step;`, biến tốc độ bị nhân 2 lần với `step` (7 * 0.1 * 0.1 = 0.07m/chu kỳ). Với `lifespan <- 350`, xe chỉ đi được 24m rồi chết trước khi tới ngã tư, kết hợp với việc reset `spawned_ids` khi có độ lệch nhỏ của timestamp làm xe sinh liên tục và đùn ứ thành búi đen tại điểm đón `{125, 230}`.
- **Giải pháp**:
  - Truyền tốc độ chuẩn m/s: `do goto target: current_target speed: speed_val;` (10 - 14 m/s).
  - Tăng thời gian sống `lifespan <- 800;` để xe thoải mái vượt qua ngã tư sang các nhánh Bắc, Đông, Tây rồi tự giải phóng ở biên bản đồ.
  - Duy trì danh sách `spawned_ids` vĩnh viễn trong phiên chạy để đảm bảo 1 xe video = đúng 1 xe GAMA (không trùng lặp).
  - Tinh giản nhãn hiển thị chỉ còn tên loài xe (`v_class`).




## 7. Chuẩn Hóa Hạ Tầng Từ Shapefile `road.shp` & Đồ Họa Phương Tiện VISSIM/SUMO
- **Vấn đề**:
  - Người dùng yêu cầu xe phải chạy trên Shapefile thực tế `road.shp` thay vì tạo geometry đường cứng trong code, đồng thời mặt đường phải rộng 3 làn theo đúng đặc thù giao thông đô thị Việt Nam (tránh tình trạng đường hẹp xe chật chội).
  - Các chữ nhãn `car`, `truck` vẽ đè lên thân xe làm rối mắt, che khuất chuyển động và gây cảm giác thiếu chuyên nghiệp.
  - Cần đảm bảo tính tương thích giữa trường JSON từ Python (`class`, `source_name`, `counts["total"]`) và bộ parser của GAML.
- **Giải pháp**:
  - Tạo tệp Shapefile `includes/road.shp` với 11 phân đoạn hoàn chỉnh (4 nhánh đường 36m + các đường nối rẽ ngã tư) với thuộc tính `lanes: 3, road_width: 36.0, is_camera: 1`. GAML tải trực tiếp thông qua `file road_shp <- shape_file("../includes/road.shp");`.
  - Phân làn xe tự nhiên theo chuẩn Việt Nam: Xe máy ưu tiên Làn 3 (sát lề) và Làn 2; Ô tô/xe tải/xe buýt chạy Làn 1 và Làn 2.
  - Loại bỏ hoàn toàn câu lệnh vẽ chữ `draw tag` trên xe. Toàn bộ thông số giám sát được gom về bảng HUD Glassmorphism ở góc trên bên trái màn hình.
  - Đồ họa tác tử chuyên nghiệp: Thân xe chassis sắc nét bo góc theo màu đặc trưng, kính chắn gió/cabin màu khói sẫm, dải đèn pha trước vàng sáng ấm, tự động xoay mượt mà theo góc lái `heading`.

## 8. Lỗi Tắc Nghẽn Đồng Bộ Do Cache ID Bền Vững Quá Mức (Session Reset & Video Loop)
- **Vấn đề**: Khi lưu `spawned_ids` vĩnh viễn không bao giờ reset trong phiên GAMA, nếu người dùng tắt đi bật lại script YOLO (`detect_and_sync.py`) hoặc video lặp lại chu kỳ mới, bộ tracker của YOLO (ByteTrack) sẽ đánh số ID lại từ đầu (1, 2, 3...). Do toàn bộ các ID này đã nằm sẵn trong `spawned_ids` của GAMA từ lần chạy trước, điều kiện `!(spawned_ids contains v_id)` trả về False cho toàn bộ xe trong khung hình. Kết quả là bên YOLO phát hiện đầy đủ xe, tệp JSON ghi bình thường nhưng GAMA không sinh bất kỳ chiếc xe nào (kết nối trông như bị gãy).
- **Giải pháp**:
  - Script Python sinh biến `session_id = int(time.time())` mỗi lần khởi chạy và truyền vào tệp JSON.
  - GAMA theo dõi `session_id`: khi phát hiện Session ID mới, GAMA lập tức hủy các xe cũ còn sót lại, làm mới `spawned_ids` và đón xe ngay từ frame đầu tiên.
  - Theo dõi `timestamp`: nếu thời gian thụt lùi quá 5 giây (video lặp chu kỳ mới), tự động làm mới `spawned_ids`.
  - Kết hợp kiểm tra xe đang chạy trên bản đồ `active_ids <- (vehicle collect each.vehicle_id)` và giới hạn kích thước mảng cache `spawned_ids` (xoay vòng sau 150 xe) để vừa chống sinh trùng lặp vừa không làm kẹt ID của các xe mới.

## 9. Định Hướng Trục Tác Tử (Heading Convention) & Chống Chồng Đè Tác Tử (Car-Following Spacing)
- **Vấn đề**:
  1. Xe bị nằm ngang (đi ngang như cua bò) thay vì dọc theo đường: Trong GAMA, góc `heading = 0.0` chỉ hướng Đông (+X) và `270.0` chỉ hướng Bắc (-Y). Khi vẽ bằng `rectangle(w, l)` với `w < l` rồi xoay theo `heading`, kích thước chiều dài và chiều rộng bị đảo ngược khi xe di chuyển trục Bắc-Nam. Hơn nữa, góc ban đầu đặt `heading <- 0.0` làm xe hướng sang Đông trong khi đang chạy lên Bắc.
  2. Các xe xuất hiện từ video bị đùn cục, đi chồng lên nhau: Khi camera phát hiện 10-15 xe ở cùng 1 khung hình, việc gán cứng vị trí xuất phát tại `y=285` khiến toàn bộ xe trong cùng làn bị sinh đè lên nhau. Trong quá trình chạy, các xe di chuyển cùng tốc độ nên tiếp tục dính chặt vào nhau do thiếu cơ chế bám đuôi an toàn (car-following model).
- **Giải pháp**:
  1. Đổi thứ tự tham số vẽ hình học: `rectangle(v_length, v_width) rotated_by heading`. Khi `heading = 270.0` (hướng Bắc), chiều dài `v_length` (4.8m) chạy dọc theo trục Y của đường, chiều rộng `v_width` (2.1m) nằm gọn trong lòng làn đường. Đặt góc khởi tạo ban đầu `heading <- 270.0`.
  2. Bố trí dải đèn pha trước tại cản trước (`location + {cos(heading)*d, sin(heading)*d}`) và đèn hậu tại cản sau (`location - {cos(heading)*d, sin(heading)*d}`).
  3. Phân bố vị trí sinh `spawn_y` theo tọa độ `cam_norm_y` từ camera (`195m .. 285m`), kết hợp quét an toàn: nếu làn đã có xe trong khoảng cách `v_length + 3.0m`, tự động lùi xe mới ra phía sau.
  4. Lập trình phản xạ bám đuôi an toàn trong `navigate`: quét các xe phía trước trong nón quan sát < 45 độ, nếu khoảng cách < `v_length + 1.2m` thì dừng hẳn (`speed = 0.0`), nếu khoảng cách < khoảng cách an toàn thì giảm tốc độ 40% (`speed * 0.4`), ngăn ngừa 100% hiện tượng xe đi xuyên hoặc chồng lên nhau.

## 10. Gán Vị Trí Làm Ghi Đè Heading Trong GAMA & Cổng Kiểm Tra Trạng Thái YOLO (Running Gate)
- **Vấn đề**:
  1. **Xe tự động sinh khi chưa bật YOLO**: Tệp `live_traffic.json` còn lưu vết dữ liệu phương tiện từ lần chạy trước. Khi người dùng mở mô phỏng GAMA, phản xạ `sync_from_yolo` đọc file và thấy danh sách `vehicles`, dẫn đến việc sinh xe ồ ạt ở đầu đường dù YOLO chưa khởi động.
  2. **Một số xe di chuyển hoặc đứng yên vẫn bị nằm ngang**: Trong skill `moving` của GAMA, toán tử gán `location <- {lane_x, spawn_y};` kích hoạt bộ theo dõi chuyển vị. GAMA tự động tính lại `heading` thành vector nối từ tọa độ ngẫu nhiên ban đầu của agent tới vị trí mới, ghi đè hoàn toàn dòng lệnh `heading <- 270.0;` đặt ở đầu hàm. Khi xe phanh dừng do giữ khoảng cách (`actual_speed == 0.0`), lệnh `do goto` không được gọi, khiến góc xoay bị kẹt vĩnh viễn ở giá trị nằm ngang ngẫu nhiên (~0 đến 65 độ).
- **Giải pháp**:
  1. **Cổng kiểm tra trạng thái YOLO (Running Gate)**: Thêm trường `"status": "running"`, `"active": true` khi YOLO hoạt động. GAMA kiểm tra `status == "running"`; nếu không thỏa mãn, đặt `is_connected <- false`, không sinh bất kỳ phương tiện nào. Bọc vòng lặp trong `detect_and_sync.py` bằng `try...finally` để luôn ghi `status: "stopped", vehicles: []` khi kết thúc.
  2. **Trật tự gán biến không làm mất Heading**: Luôn gán `location <- {lane_x, spawn_y};` trước, sau đó mới gán `heading <- 270.0;`.
  3. **Cập nhật Heading liên tục theo Waypoint**: Trong `reflex navigate`, ở mỗi chu kỳ luôn gán `heading <- float(self towards waypoints[current_wp_idx]);` trước khi xét phanh dừng, đảm bảo góc quay luôn hướng thẳng theo làn đường.
  4. **Góc vẽ độc lập `draw_angle` & Đồ họa xe đa lớp**: Trong `aspect default`, tính `float draw_angle <- (current_wp_idx < length(waypoints)) ? float(self towards waypoints[current_wp_idx]) : heading;` và xoay chassis, windshield, roof, đèn pha LED trước và đèn hậu sau theo `draw_angle`.
## 11. Cẩn Trọng Khi Chỉnh Sửa Khối Lệnh Điều Khiển Trong Python (Guard Clause Tránh `IndentationError`)
- **Vấn đề**: Khi lồng một khối mã lớn vào trong câu lệnh điều kiện `if not is_paused:` trong vòng lặp chính của OpenCV/YOLO, nếu chỉ thêm dòng `if` mà không tăng thụt lề cho toàn bộ hơn 160 dòng lệnh xử lý bên dưới, Python sẽ ném ngoại lệ cú pháp:
  `IndentationError: expected an indented block after 'if' statement on line 221`.
- **Giải pháp**:
  - Với các trạng thái như tạm dừng (Pause loop) trong xử lý video, áp dụng mẫu thiết kế kiểm tra sớm (Guard Clause) ngay ở đầu vòng lặp:
    ```python
    if is_paused:
        if display_frame is not None:
            cv2.imshow("...", display_frame)
        key = cv2.waitKey(50) & 0xFF
        if key == ord('p') or key == 32:
            is_paused = not is_paused
        continue
    # Khối mã đọc frame và tracking bên dưới giữ nguyên mức thụt lề chuẩn
    ```
  - Mẫu thiết kế này giữ nguyên cấu trúc thụt lề của toàn bộ khối mã đọc video và YOLO bên dưới, triệt tiêu nguy cơ lỗi thụt lề.
## 12. GAML File Resolution Trong GAMA GUI: Tránh `file_exists` Tương Đối & Sử Dụng Chuẩn Nội Bộ Dự Án `../`
- **Vấn đề**:
  1. Trong GAMA GUI trên macOS, toán tử `file_exists("../roi_telemetry.json")` kiểm tra tương đối theo thư mục làm việc của Java VM (`/Applications/Gama.app/Contents/MacOS`), không phải theo thư mục của mô hình GAML. Do đó `file_exists` luôn trả về `false`.
  2. Khi fallback về `../../roi_telemetry.json`, Eclipse Workspace Resource Manager chặn đứng vì đường dẫn vượt ra ngoài ranh giới dự án, ném `IllegalArgumentException: Path must include project and resource name`. Ngoại lệ này bị khối `try...catch` bắt lấy khiến GAMA không thể nạp file, hiển thị vĩnh viễn: `CHƯA CÓ DỮ LIỆU` / `CHƯA KẾT NỐI`.
  3. Khi chỉnh sửa file GAML từ bên ngoài, nếu người dùng không Refresh (F5) hoặc không đóng/mở lại tab trong GAMA GUI, GAMA tiếp tục chạy buffer cũ trong RAM.
- **Giải pháp**:
  - Đặt tệp JSON ngay trong thư mục gốc của GAMA project (`gama_roi_pressure_trafficsi/roi_telemetry.json`).
  - Đường dẫn trong GAML viết chuẩn nội bộ trực tiếp: `string telemetry_path <- "../roi_telemetry.json";` (không dùng `file_exists` hay `../../`).
  - Python `calculate_roi_pressure.py` phát đa điểm tới tất cả các thư mục dự án qua `JSON_TELEMETRY_PATHS` và gán quyền `0644`.
  - Hướng dẫn người dùng: Dừng mô phỏng (nút đỏ X), đóng tab model trong GAMA và mở lại từ đĩa (hoặc bấm F5) rồi bấm Run.
