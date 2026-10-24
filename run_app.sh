#!/usr/bin/env bash
# ==============================================================================
# 1-CLICK LAUNCHER CHO BUỔI NGHIỆM THU ĐỀ TÀI NCKH
# Hệ Thống Giám Sát Digital Twin & Phân Tích Áp Lực Giao Thông (JavaFX Light Mode)
# ==============================================================================

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "======================================================================"
echo "🚀 KHỞI ĐỘNG HỆ THỐNG DIGITAL TWIN & ROI PRESSURE ANALYZER"
echo "   Chế độ: Java Desktop App (Light Mode)"
echo "   Mục đích: Nghiệm Thu Báo Cáo Đề Tài NCKH"
echo "======================================================================"

# Kiểm tra Python Virtual Environment
if [ -f "$DIR/yolov8-env/bin/python" ]; then
    PYTHON_EXEC="$DIR/yolov8-env/bin/python"
elif [ -f "$DIR/venv/bin/python" ]; then
    PYTHON_EXEC="$DIR/venv/bin/python"
else
    PYTHON_EXEC="python3"
fi

echo "✓ Môi trường Python: $PYTHON_EXEC"

# Khởi chạy Maven JavaFX
echo "✓ Đang biên dịch và mở ứng dụng Java Desktop..."
cd "$DIR/java-traffic-twin"
mvn javafx:run
