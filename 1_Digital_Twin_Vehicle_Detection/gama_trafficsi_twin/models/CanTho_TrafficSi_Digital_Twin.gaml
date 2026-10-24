/**
 * =============================================================================
 * DỰ ÁN DIGITAL TWIN CẦN THƠ - BẢN ĐỒ GIS THỰC TẾ NGUYỄN VĂN CỪ & NGUYỄN VĂN LINH
 * Mô hình mô phỏng giao thông số hóa thời gian thực tích hợp YOLOv8
 * Nạp từ Shapefiles thực tế: includes/road.shp, building.shp, traffic_light.shp
 * =============================================================================
 */

model CanTho_TrafficSi_Digital_Twin

global {
    // -------------------------------------------------------------------------
    // 1. TÀI NGUYÊN GIS THỰC TẾ CẦN THƠ (NGUYỄN VĂN CỪ - NGUYỄN VĂN LINH)
    // -------------------------------------------------------------------------
    file road_shp        <- shape_file("../includes/road.shp");
    file building_shp    <- shape_file("../includes/building.shp");
    file signal_shp      <- shape_file("../includes/traffic_light.shp");
    
    // Ranh giới không gian mô phỏng bao quát toàn bộ mạng lưới đường và công trình
    geometry shape       <- envelope(road_shp) + 15.0;
    graph road_network;
    
    // Bước thời gian mô phỏng (0.1s mỗi chu kỳ = 10 FPS đồng bộ chuẩn)
    float step <- 0.1 #s;
    
    // -------------------------------------------------------------------------
    // 2. KẾT NỐI ĐỒNG BỘ THỜI GIAN THỰC YOLOv8 (LIVE TELEMETRY BRIDGE)
    // -------------------------------------------------------------------------
    string json_path <- "../live_traffic.json";
    
    bool is_connected <- false;
    int total_detected <- 0;
    int car_count <- 0;
    int moto_count <- 0;
    int bus_count <- 0;
    int truck_count <- 0;
    float cv_fps <- 0.0;
    string source_name <- "Chờ YOLOv8...";
    string source_type <- "video";
    
    // Bộ nhớ phiên làm việc chống đùn và chống sinh trùng lặp
    list<int> spawned_ids <- [];
    int total_spawned_cumulative <- 0;
    int current_session_id <- 0;
    float last_yolo_timestamp <- 0.0;
    
    // Danh sách các nút giao thông (intersections) và nút biên thoát (exit nodes)
    list<intersection> edge_nodes <- [];
    list<intersection> signal_nodes <- [];
    road camera_approach_road <- nil;
    
    init {
        write "============================================================";
        write "🏙️ DIGITAL TWIN CẦN THƠ: GIS NGUYỄN VĂN CỪ & NGUYỄN VĂN LINH";
        write "✓ Shapefile Tuyến đường : ../includes/road.shp";
        write "✓ Shapefile Công trình  : ../includes/building.shp";
        write "✓ Shapefile Đèn tín hiệu: ../includes/traffic_light.shp";
        write "✓ Tệp đồng bộ JSON      : " + json_path;
        write "============================================================";
        
        // 1. Nạp các tuyến đường
        create road from: road_shp with: [
            name       :: string(read("name")),
            highway    :: string(read("highway")),
            lanes      :: int(read("lanes")),
            oneway     :: string(read("oneway"))
        ];
        
        // 2. Nạp các công trình kiến trúc đô thị
        create building from: building_shp;
        
        // 3. Xây dựng đồ thị mạng lưới đường giao thông
        graph temp_graph <- as_edge_graph(road);
        loop v over: temp_graph.vertices {
            create intersection with: [shape::point(v)] {
                is_traffic_signal <- false;
            }
        }
        road_network <- as_driving_graph(road, intersection);
        
        // 4. Liên kết các đường vào / ra của từng nút giao
        ask intersection {
            roads_in  <- road where (last(each.shape.points) distance_to location < 1.0);
            roads_out <- road where (first(each.shape.points) distance_to location < 1.0);
        }
        
        // 5. Nạp vị trí đèn tín hiệu giao thông thực tế
        loop sg over: list<geometry>(signal_shp.contents) {
            intersection target_node <- intersection closest_to sg;
            if (target_node != nil) {
                target_node.is_traffic_signal <- true;
                create traffic_light_visual {
                    location <- sg.location;
                    my_node <- target_node;
                }
            }
        }
        
        // Phân loại các nút giao có đèn và các nút biên thoát
        signal_nodes <- intersection where (each.is_traffic_signal);
        edge_nodes <- intersection where (!each.is_traffic_signal and !empty(each.roads_in));
        if (empty(edge_nodes)) {
            edge_nodes <- intersection where (!each.is_traffic_signal);
        }
        
        // 6. Xác định tuyến đường tiếp cận của camera (nhánh đón xe vào nút giao)
        camera_approach_road <- road with_max_of (each.shape.perimeter);
        write "✓ Tuyến đường đón xe Camera: " + (camera_approach_road != nil ? camera_approach_road.name : "Mặc định") + " (Dài: " + round(camera_approach_road.shape.perimeter) + "m)";
    }
    
    // -------------------------------------------------------------------------
    // PHẢN XẠ ĐỒNG BỘ DỮ LIỆU TỪ YOLO (10 LẦN / GIÂY)
    // -------------------------------------------------------------------------
    reflex sync_from_yolo {
        try {
            file live_file <- json_file(json_path);
            if (live_file != nil) {
                map data <- map(live_file.contents);
                
                if (data != nil and data contains_key "vehicles") {
                    // CỔNG KIỂM TRA TRẠNG THÁI YOLO (Running Gate):
                    // Chỉ sinh xe khi YOLO đang thực sự chạy (status = "running" hoặc active = true)
                    bool yolo_active <- false;
                    if (data contains_key "status") {
                        yolo_active <- (string(data["status"]) = "running");
                    } else if (data contains_key "active") {
                        yolo_active <- bool(data["active"]);
                    }
                    
                    if (!yolo_active) {
                        is_connected <- false;
                        total_detected <- 0;
                        car_count <- 0;
                        moto_count <- 0;
                        bus_count <- 0;
                        truck_count <- 0;
                        return;
                    }
                    
                    is_connected <- true;
                    
                    // Phát hiện phiên YOLO mới chạy -> Làm mới danh sách xe
                    if (data contains_key "session_id") {
                        int sess <- int(data["session_id"]);
                        if (current_session_id != 0 and sess != current_session_id) {
                            write "🔄 [DIGITAL TWIN] Phát hiện phiên YOLO mới (Session " + sess + ") -> ĐỒNG BỘ TỨC THÌ!";
                            ask vehicle { do die; }
                            spawned_ids <- [];
                            total_spawned_cumulative <- 0;
                        }
                        current_session_id <- sess;
                    }
                    
                    // Phát hiện video lặp chu kỳ -> Làm mới bộ nhớ đón xe
                    if (data contains_key "timestamp") {
                        float ts <- float(data["timestamp"]);
                        if (last_yolo_timestamp > 0.0 and ts < (last_yolo_timestamp - 5.0)) {
                            write "🔄 [DIGITAL TWIN] Video lặp lại chu kỳ mới -> Làm mới bộ nhớ đón xe!";
                            spawned_ids <- [];
                        }
                        last_yolo_timestamp <- ts;
                    }
                    
                    cv_fps <- (data contains_key "fps") ? float(data["fps"]) : 0.0;
                    source_name <- (data contains_key "source_name") ? string(data["source_name"]) : "YOLOv8 Stream";
                    source_type <- (data contains_key "source_type") ? string(data["source_type"]) : "video";
                    
                    if (data contains_key "counts") {
                        map counts_map <- map(data["counts"]);
                        if (counts_map != nil) {
                            total_detected <- (counts_map contains_key "total") ? int(counts_map["total"]) : 0;
                            car_count   <- (counts_map contains_key "car") ? int(counts_map["car"]) : 0;
                            moto_count  <- (counts_map contains_key "motorcycle") ? int(counts_map["motorcycle"]) : 0;
                            bus_count   <- (counts_map contains_key "bus") ? int(counts_map["bus"]) : 0;
                            truck_count <- (counts_map contains_key "truck") ? int(counts_map["truck"]) : 0;
                        }
                    } else if (data contains_key "total_detected") {
                        total_detected <- int(data["total_detected"]);
                    }
                    
                    list detected_list <- list(data["vehicles"]);
                    list<int> active_ids <- (vehicle collect each.vehicle_id);
                    
                    // Duyệt từng xe từ camera: ĐẢM BẢO CHÍNH XÁC 1 XE VIDEO = 1 XE GAMA
                    loop v_raw over: detected_list {
                        map v_info <- map(v_raw);
                        int v_id <- int(v_info["id"]);
                        string v_class <- (v_info contains_key "class") ? string(v_info["class"]) : ((v_info contains_key "class_name") ? string(v_info["class_name"]) : "car");
                        float v_norm_x <- (v_info contains_key "norm_x") ? float(v_info["norm_x"]) : 0.5;
                        float v_norm_y <- (v_info contains_key "norm_y") ? float(v_info["norm_y"]) : 0.8;
                        
                        // Điều kiện sinh xe: Không sinh trùng ID đang chạy và chưa sinh trong chu kỳ này
                        if (!(active_ids contains v_id) and !(spawned_ids contains v_id)) {
                            add v_id to: spawned_ids;
                            total_spawned_cumulative <- total_spawned_cumulative + 1;
                            
                            create vehicle number: 1 {
                                vehicle_id <- v_id;
                                v_type <- v_class;
                                cam_norm_x <- v_norm_x;
                                cam_norm_y <- v_norm_y;
                                do setup_vehicle_profile;
                            }
                            write "🚗 [SINH XE LIVE NGUYỄN VĂN CỪ] ID=" + v_id + " (" + v_class + ") -> Đang chạy vào nút giao!";
                        }
                    }
                    
                    if (length(spawned_ids) > 150) {
                        spawned_ids <- copy_between(spawned_ids, length(spawned_ids) - 80, length(spawned_ids));
                    }
                }
            }
        } catch {
            is_connected <- false;
        }
    }
}

/**
 * =============================================================================
 * SPECIES ROAD: TUYẾN ĐƯỜNG ĐÔ THỊ THỰC TẾ (NGUYỄN VĂN CỪ / NGUYỄN VĂN LINH)
 * =============================================================================
 */
species road skills: [road_skill] {
    string name;
    string highway;
    int lanes <- 2;
    string oneway <- "yes";
    float road_width <- 14.0;
    
    aspect default {
        // Lòng đường nhựa màu slate xám hiện đại
        draw shape + (road_width / 2) color: rgb(226, 232, 240) border: rgb(148, 163, 184);
        // Vạch tim đường màu vàng
        draw shape color: rgb(234, 179, 8) width: 1.5;
    }
}

/**
 * SPECIES BUILDING: KHỐI CÔNG TRÌNH KIẾN TRÚC XUNG QUANH NÚT GIAO
 */
species building {
    rgb b_color <- rgb(241, 245, 249);
    
    aspect default {
        draw shape color: b_color border: rgb(203, 213, 225);
    }
}

/**
 * SPECIES TRAFFIC_LIGHT_VISUAL: ĐÈN TÍN HIỆU GIAO THÔNG TẠI NÚT GIAO
 */
species traffic_light_visual {
    intersection my_node;
    rgb signal_color <- rgb(34, 197, 94); // Mặc định xanh mở đường
    
    aspect default {
        draw circle(4.0) at: location color: signal_color border: rgb(15, 23, 42);
        draw circle(1.8) at: location color: rgb(255, 255, 255);
    }
}

/**
 * SPECIES INTERSECTION: NÚT GIAO KẾT NỐI MẠNG LƯỚI ĐƯỜNG
 */
species intersection skills: [intersection_skill] {
    bool is_traffic_signal <- false;
}

/**
 * =============================================================================
 * SPECIES VEHICLE: TÁC TỬ PHƯƠNG TIỆN DIGITAL TWIN TRÊN BẢN ĐỒ THỰC TẾ
 * =============================================================================
 */
species vehicle skills: [driving] {
    int vehicle_id;
    string v_type <- "car";
    float cam_norm_x <- 0.5;
    float cam_norm_y <- 0.8;
    
    float v_length <- 4.8;
    float v_width  <- 2.1;
    rgb v_color    <- rgb(37, 99, 235);
    float desired_speed <- 12.0; // ~43 km/h
    
    intersection target_exit <- nil;
    int lifespan <- 1200;
    
    // Cài đặt thông số chi tiết theo từng loại xe
    action setup_vehicle_profile {
        if (v_type = "motorcycle") {
            v_length <- 2.2;
            v_width  <- 0.9;
            v_color  <- rgb(2, 132, 199);
            desired_speed <- rnd(10.5, 13.5);
        } else if (v_type = "car") {
            v_length <- 4.8;
            v_width  <- 2.1;
            v_color  <- rgb(37, 99, 235);
            desired_speed <- rnd(11.0, 14.0);
        } else if (v_type = "bus") {
            v_length <- 11.5;
            v_width  <- 2.8;
            v_color  <- rgb(22, 163, 74);
            desired_speed <- rnd(8.5, 10.5);
        } else if (v_type = "truck") {
            v_length <- 8.5;
            v_width  <- 2.6;
            v_color  <- rgb(217, 119, 6);
            desired_speed <- rnd(8.0, 10.0);
        }
        
        max_speed <- desired_speed;
        speed <- desired_speed;
        
        // Xác định vị trí xuất phát trên tuyến đường đón xe của Camera
        if (camera_approach_road != nil and !empty(camera_approach_road.shape.points)) {
            point start_p <- first(camera_approach_road.shape.points);
            point end_p   <- last(camera_approach_road.shape.points);
            
            // Dàn trải vị trí Y dọc theo tuyến đường đón xe theo cam_norm_y
            float road_len <- camera_approach_road.shape.perimeter;
            float dist_along <- road_len * (0.15 + (cam_norm_y * 0.70));
            
            point base_pt <- (start_p + (end_p - start_p) * (dist_along / road_len));
            
            // Dịch chuyển nhẹ ngang làn theo cam_norm_x
            float lateral_offset <- (cam_norm_x - 0.5) * (camera_approach_road.road_width * 0.45);
            float base_angle <- float(start_p towards end_p);
            point final_pt <- base_pt + {cos(base_angle + 90.0) * lateral_offset, sin(base_angle + 90.0) * lateral_offset};
            
            // Gán vị trí trước, sau đó gán heading để tránh bị moving/driving skill ghi đè
            location <- final_pt;
            heading <- base_angle;
        } else {
            location <- (camera_approach_road != nil) ? camera_approach_road.location : {100.0, 100.0};
            heading <- 270.0;
        }
        
        // Chọn một nút thoát đích ngẫu nhiên trong mạng lưới để xe lưu thông qua ngã tư
        if (!empty(edge_nodes)) {
            target_exit <- one_of(edge_nodes);
        }
    }
    
    // Điều hướng lưu thông và bám đuôi an toàn (Car-Following)
    reflex navigate {
        lifespan <- lifespan - 1;
        if (lifespan <= 0) {
            do die;
            return;
        }
        
        // Tìm đường đi đến nút đích nếu chưa có lộ trình
        if (current_path = nil and target_exit != nil) {
            do compute_path graph: road_network target: target_exit;
            if (current_path = nil) {
                // Thử đổi sang nút đích khác nếu nút hiện tại không kết nối được
                target_exit <- one_of(edge_nodes - target_exit);
                if (target_exit != nil) {
                    do compute_path graph: road_network target: target_exit;
                }
            }
        }
        
        // --- CƠ CHẾ CHỐNG ĐI CHỒNG LÊN NHAU (CAR-FOLLOWING) ---
        float safe_distance <- v_length + 4.0;
        list<vehicle> near_vehs <- (vehicle at_distance safe_distance) - self;
        bool must_stop <- false;
        bool must_slow <- false;
        
        loop other over: near_vehs {
            float ang <- float(self towards other);
            float diff_ang <- abs(ang - heading) mod 360.0;
            if (diff_ang > 180.0) { diff_ang <- 360.0 - diff_ang; }
            
            if (diff_ang < 45.0) {
                float dist <- self distance_to other;
                if (dist < (v_length + 1.5)) {
                    must_stop <- true;
                } else if (dist < safe_distance) {
                    must_slow <- true;
                }
            }
        }
        
        float actual_speed <- desired_speed;
        if (must_stop) {
            actual_speed <- 0.0;
        } else if (must_slow) {
            actual_speed <- desired_speed * 0.4;
        }
        
        if (actual_speed > 0.0 and target_exit != nil) {
            do goto target: target_exit.location on: road_network speed: actual_speed;
            
            // Đến gần đích thì giải phóng tác tử tự nhiên
            if (location distance_to target_exit.location < 8.0) {
                do die;
            }
        }
    }
    
    // Đồ họa tác tử xe chuẩn mô phỏng (SUMO/VISSIM):
    // Xe xoay chuẩn 100% dọc theo làn đường ở mọi vị trí
    aspect default {
        float draw_angle <- heading;
        
        // 1. Thân xe chính (Chassis) - Bo viền sắc nét
        draw (rectangle(v_length, v_width) rotated_by draw_angle) color: v_color border: rgb(30, 41, 59);
        
        // 2. Kính chắn gió / Cabin sẫm màu
        draw (rectangle(v_length * 0.50, v_width * 0.80) rotated_by draw_angle) color: rgb(15, 23, 42, 230);
        
        // 3. Nóc xe / Mui xe (Roof) màu bóng ở giữa cabin
        draw (rectangle(v_length * 0.28, v_width * 0.65) rotated_by draw_angle) color: v_color - 20;
        
        // 4. Dải đèn pha LED trước màu vàng sáng tại cản trước
        point front_pt <- location + {cos(draw_angle) * (v_length * 0.46), sin(draw_angle) * (v_length * 0.46)};
        draw (rectangle(0.35, v_width * 0.75) rotated_by draw_angle) at: front_pt color: rgb(254, 240, 138);
        
        // 5. Dải đèn hậu LED đỏ tại cản sau
        point rear_pt <- location - {cos(draw_angle) * (v_length * 0.46), sin(draw_angle) * (v_length * 0.46)};
        draw (rectangle(0.35, v_width * 0.75) rotated_by draw_angle) at: rear_pt color: rgb(239, 68, 68);
    }
}

/**
 * =============================================================================
 * GIAO DIỆN MÔ PHỎNG & BẢNG HUD TELEMETRY DIGITAL TWIN CẦN THƠ
 * =============================================================================
 */
experiment CanThoTrafficSiExperiment type: gui {
    output {
        display "CanTho_TrafficSi_GIS_Viewer" type: 2d background: rgb(248, 250, 252) {
            // 1. Hiển thị các khối công trình kiến trúc xung quanh nút giao
            species building aspect: default;
            
            // 2. Hiển thị mạng lưới đường giao thông từ road.shp
            species road aspect: default;
            
            // 3. Hiển thị đèn tín hiệu giao thông thực tế
          //  species traffic_light_visual aspect: default;
            
            // 4. Hiển thị các phương tiện lưu thông thời gian thực
            species vehicle aspect: default;
            
            // 5. Bảng thông số Telemetry Digital Twin (Glassmorphism HUD Card)
        
        }
    }
}

