/**
 * =============================================================================
 * ĐỀ TÀI NCKH: DIGITAL TWIN - ĐIỀU KHIỂN TÍN HIỆU GIAO THÔNG THÍCH ỨNG
 * DỰ ÁN GAMA 3: ROI PRESSURE TRÊN BẢN ĐỒ GIS THỰC TẾ TRAFFICSI
 * =============================================================================
 * Bản đồ: Nguyễn Văn Cừ - Nguyễn Văn Linh (shapefile TrafficSi, WGS84).
 * GAMA tự reproject WGS84 -> UTM 48N (EPSG:32648) theo preference mặc định,
 * nên các kích thước mét (ROI 9 x 94 m, đường 14 m) giữ đúng tỉ lệ.
 *
 * Nội dung:
 *   1. Nạp road.shp + building.shp; hiển thị light mode đồng bộ folder 1.
 *   2. Không hiển thị đèn tín hiệu, không sinh xe; giữ traffic_light.shp
 *      trong includes để tham chiếu.
 *   3. ROI 9 x 94 m trên nhánh SE - Nguyễn Văn Linh inbound, cách nút giao 8 m.
 *   4. Đọc ../../roi_telemetry.json + heartbeat 2 giây do Python ghi.
 *   5. HUD card tự scale theo kích thước bản đồ để chữ 9-11 px không tràn.
 * =============================================================================
 */

model CanTho_ROI_TrafficSi_Digital_Twin

global {
    // -------------------------------------------------------------------------
    // 1. TÀI NGUYÊN GIS THỰC TẾ TRAFFICSI
    // -------------------------------------------------------------------------
    file road_shp     <- shape_file("../includes/road.shp");
    file building_shp <- shape_file("../includes/building.shp");

    geometry road_env <- envelope(road_shp);
    geometry shape    <- road_env + 15.0;
    float step        <- 0.1 #s;

    // -------------------------------------------------------------------------
    // 2. TELEMETRY ROI PRESSURE
    // -------------------------------------------------------------------------
    string telemetry_path <- "../roi_telemetry.json";

    float occupancy_pct     <- 0.0;
    float queue_length_m    <- 0.0;
    float pressure_score    <- 0.0;
    string traffic_status   <- "CHƯA KẾT NỐI";
    int status_code         <- 0;
    int vehicles_in_roi     <- 0;
    int dwelling_vehicles   <- 0;
    float cv_fps            <- 0.0;
    string source_name      <- "Đang đợi YOLOv8...";
    bool is_connected       <- false;
    bool has_data           <- false;
    float data_age_s        <- 999.0;
    float last_ts_s         <- 0.0;
    float stale_after_s     <- 2.0;

    // -------------------------------------------------------------------------
    // 3. THAM SỐ ROI TRÊN NHÁNH SE - NGUYỄN VĂN LINH
    // -------------------------------------------------------------------------
    float roi_length_m      <- 94.0;
    float roi_width_m       <- 9.0;
    float roi_stop_offset_m <- 8.0;
    float queue_bar_max_m   <- 94.0;

    road approach_road <- nil;
    point stop_p        <- nil;
    point approach_dir  <- nil;
    point left_dir      <- nil;
    point right_dir     <- nil;
    point roi_downstream <- nil;
    point roi_upstream   <- nil;
    point roi_center     <- nil;
    point queue_bar_start <- nil;
    point roi_label_pos   <- nil;
    point queue_label_pos <- nil;

    // -------------------------------------------------------------------------
    // 4. HUD TỰ SCALE THEO BẢN ĐỒ (tránh tràn chữ trên map ~495 x 456 m)
    // -------------------------------------------------------------------------
    float hud_size  <- 0.50 * min(shape.width, shape.height);
    float hud_scale <- hud_size / 102.0;
    point hud_origin <- {
        shape.location.x - shape.width / 2.0 + 8.0,
        shape.location.y - shape.height / 2.0 + 8.0
    };

    init {
        write "============================================================";
        write "🏙️ DIGITAL TWIN ROI PRESSURE - BẢN ĐỒ TRAFFICSI NVC-NVL";
        write "✓ Road shapefile     : ../includes/road.shp";
        write "✓ Building shapefile : ../includes/building.shp";
        write "✓ Telemetry JSON     : " + telemetry_path;
        write "✓ Heartbeat tối đa   : " + string(stale_after_s with_precision 1) + " giây";
        write "✓ Kích thước bản đồ  : " + string(shape.width with_precision 1) + "m x " + string(shape.height with_precision 1) + "m";
        write "✓ HUD card           : " + string(hud_size with_precision 1) + "m (scale " + string(hud_scale with_precision 2) + ")";
        write "============================================================";

        create road from: road_shp with: [
            name    :: string(read("name")),
            highway :: string(read("highway")),
            lanes   :: int(read("lanes"))
        ];
        create building from: building_shp;

        write "✓ Đã nạp " + string(length(road)) + " tuyến đường, " + string(length(building)) + " công trình.";
        do setup_roi;
    }

    // Xác định nhánh vào SE - Nguyễn Văn Linh và dựng ROI 9 x 94 m.
    action setup_roi {
        point map_center <- shape.location;

        // Chỉ xét Nguyễn Văn Linh (highway=trunk) và nhánh inbound hướng SE.
        // Lưu ý: trục y của GAMA trên bản đồ này hướng xuống, nên SE có y > tâm.
        list<road> candidates <- road where (
            each.highway = "trunk" and
            (first(each.shape.points) distance_to map_center) > (last(each.shape.points) distance_to map_center) and
            first(each.shape.points).x > last(each.shape.points).x and
            first(each.shape.points).y > last(each.shape.points).y
        );

        approach_road <- candidates with_max_of (each.shape.perimeter);

        if (approach_road != nil and length(approach_road.shape.points) >= 2) {
            list<point> pts <- approach_road.shape.points;
            stop_p <- last(pts);

            point prev_p <- stop_p;
            loop p over: pts {
                if (p != stop_p) {
                    prev_p <- p;
                }
            }

            float angle <- float(prev_p towards stop_p);
            approach_dir <- {cos(angle), sin(angle)};
            left_dir     <- {cos(angle + 90.0), sin(angle + 90.0)};
            right_dir    <- {cos(angle - 90.0), sin(angle - 90.0)};

            roi_downstream <- stop_p - approach_dir * roi_stop_offset_m;
            roi_upstream   <- roi_downstream - approach_dir * roi_length_m;
            roi_center     <- roi_downstream - approach_dir * (roi_length_m / 2.0);

            point p1 <- roi_downstream + left_dir * (roi_width_m / 2.0);
            point p2 <- roi_downstream - left_dir * (roi_width_m / 2.0);
            point p3 <- roi_upstream   - left_dir * (roi_width_m / 2.0);
            point p4 <- roi_upstream   + left_dir * (roi_width_m / 2.0);

            create roi_zone number: 1 {
                shape   <- polygon([p1, p2, p3, p4]);
                zone_id <- "ROI_SE_NVL_Approach";
            }

            queue_bar_start <- roi_downstream + left_dir * (roi_width_m / 2.0 + 1.5);
            roi_label_pos   <- roi_center + right_dir * (roi_width_m / 2.0 + 8.0);
            queue_label_pos <- roi_label_pos - approach_dir * 14.0;

            write "✓ Nhánh ROI          : " + approach_road.name + " (SE inbound, " + string(approach_road.shape.perimeter with_precision 1) + "m)";
            write "✓ ROI                : " + string(roi_length_m) + "m x " + string(roi_width_m) + "m, cách nút giao " + string(roi_stop_offset_m) + "m";
        } else {
            write "⚠ Không xác định được nhánh ROI SE - kiểm tra lại shapefile road.shp.";
        }
    }

    // Phản xạ đọc telemetry thời gian thực + kiểm tra heartbeat timestamp
    reflex sync_roi_telemetry {
        try {
            file tel_file <- json_file(telemetry_path);
            if (tel_file != nil and tel_file.contents != nil) {
                map data <- map(tel_file.contents);

                if (data != nil and length(data) > 0) {
                    string sname    <- (data contains_key "source_name") ? string(data["source_name"]) : "YOLO Stream";
                    float fps_val   <- (data contains_key "fps") ? float(data["fps"]) : 0.0;
                    float occ_val   <- (data contains_key "roi_occupancy_pct") ? float(data["roi_occupancy_pct"]) : 0.0;
                    float qlen_val  <- (data contains_key "queue_length_m") ? float(data["queue_length_m"]) : 0.0;
                    float pscore_val <- (data contains_key "pressure_score") ? float(data["pressure_score"]) : 0.0;
                    string stext_val <- (data contains_key "status") ? string(data["status"]) : "CHƯA RÕ";
                    int scode_val   <- (data contains_key "status_code") ? int(data["status_code"]) : 1;
                    int vin_val     <- (data contains_key "vehicles_in_roi") ? int(data["vehicles_in_roi"]) : 0;
                    int dwell_val   <- (data contains_key "dwelling_vehicles") ? int(data["dwelling_vehicles"]) : 0;
                    float ts_s      <- (data contains_key "timestamp") ? float(data["timestamp"]) : 0.0;

                    source_name    <- sname;
                    cv_fps         <- fps_val;
                    occupancy_pct  <- occ_val;
                    queue_length_m <- qlen_val;
                    pressure_score <- pscore_val;
                    traffic_status <- stext_val;
                    status_code    <- scode_val;
                    vehicles_in_roi <- vin_val;
                    dwelling_vehicles <- dwell_val;
                    last_ts_s      <- ts_s;
                    data_age_s     <- max(0.0, (gama.machine_time / 1000.0) - last_ts_s);
                    has_data       <- true;
                    is_connected   <- data_age_s <= stale_after_s;
                }
            }
        } catch {
            is_connected <- false;
            if (has_data) {
                data_age_s <- max(0.0, (gama.machine_time / 1000.0) - last_ts_s);
            } else {
                data_age_s <- 999.0;
            }
        }
    }
}

// -----------------------------------------------------------------------------
// TUYẾN ĐƯỜNG THỰC TẾ TỪ ROAD.SHP
// -----------------------------------------------------------------------------
species road {
    string name;
    string highway;
    int lanes <- 2;
    float road_width <- 14.0;

    aspect default {
        draw shape + (road_width / 2.0) color: rgb(226, 232, 240) border: rgb(148, 163, 184);
        draw shape color: rgb(234, 179, 8) width: 1.5;
    }
}

// -----------------------------------------------------------------------------
// CÔNG TRÌNH THỰC TẾ TỪ BUILDING.SHP
// -----------------------------------------------------------------------------
species building {
    aspect default {
        draw shape color: rgb(241, 245, 249) border: rgb(203, 213, 225);
    }
}

// -----------------------------------------------------------------------------
// VÙNG ROI TRÊN NHÁNH SE - NGUYỄN VĂN LINH
// -----------------------------------------------------------------------------
species roi_zone {
    string zone_id;

    aspect default {
        bool is_fresh <- has_data and is_connected;

        rgb dynamic_fill <- rgb(100, 116, 139, 50);
        rgb dynamic_border <- rgb(148, 163, 184);

        if (is_fresh) {
            dynamic_fill <- rgb(34, 197, 94, 80);
            dynamic_border <- rgb(22, 163, 74);

            if (status_code = 2) {
                dynamic_fill <- rgb(245, 158, 11, 130);
                dynamic_border <- rgb(217, 119, 6);
            } else if (status_code = 3) {
                dynamic_fill <- rgb(239, 68, 68, 160);
                dynamic_border <- rgb(220, 38, 38);
            }
        }

        draw shape color: dynamic_fill border: dynamic_border width: 2.5;

        if (is_fresh and queue_length_m > 0.0) {
            float bar_len <- min(queue_length_m, queue_bar_max_m);
            draw line([queue_bar_start, queue_bar_start - approach_dir * bar_len]) color: rgb(225, 29, 72) width: 5.0;
        }

        if (is_fresh) {
            string roi_label <- "ROI: " + string(pressure_score with_precision 1) + " (" + traffic_status + ")";
            draw roi_label color: rgb(15, 23, 42) size: 10.0 at: roi_label_pos;

            string q_label <- "Hàng chờ: " + string(queue_length_m with_precision 1) + "m | Mật độ: " + string(occupancy_pct with_precision 1) + "%";
            draw q_label color: rgb(180, 83, 9) size: 9.0 at: queue_label_pos;
        } else {
            draw "ROI: -- (CHỜ DỮ LIỆU)" color: rgb(100, 116, 139) size: 10.0 at: roi_label_pos;
        }
    }
}

// -----------------------------------------------------------------------------
// GIAO DIỆN TRỰC QUAN HÓA & NGHIỆM THU
// -----------------------------------------------------------------------------
experiment CanThoROITrafficSiExperiment type: gui {
    output {
        display "Digital Twin - ROI Pressure - TrafficSi NVC-NVL" type: 2d background: rgb(248, 250, 252) {
            // Công trình và tuyến đường thực tế
            species building aspect: default;
            species road aspect: default;

            // Vùng ROI đổi màu theo áp lực thời gian thực
            species roi_zone aspect: default;

            // HUD card tự scale theo bản đồ
            
        }
    }
}
