#!/usr/bin/env python3
"""
Optimized YOLO Training Script for MacBook Air M2 (using Apple Silicon GPU / MPS)
Supports training on:
1. Aerial Traffic Dataset (dataset) - to detect vehicles from top-down views.
2. Drone Detection Dataset (drone_dataset) - to detect drones.
"""

import os
import sys
import yaml
import shutil
from pathlib import Path
from ultralytics import YOLO

BASE_DIR = Path(__file__).parent.resolve()

def setup_traffic_yaml():
    dataset_dir = BASE_DIR / "dataset"
    yaml_path = dataset_dir / "data.yaml"
    dataset_yaml = {
        "path": str(dataset_dir),
        "train": "images",
        "val": "images",
        "nc": 4,
        "names": {0: "car", 1: "motorcycle", 2: "bus", 3: "truck"}
    }
    with open(yaml_path, "w") as f:
        yaml.dump(dataset_yaml, f, default_flow_style=False)
    print(f"✅ Created/Updated traffic dataset config at: {yaml_path}")
    return yaml_path, "aerial_traffic"

def setup_drone_yaml():
    dataset_dir = BASE_DIR / "drone_dataset"
    yaml_path = dataset_dir / "data.yaml"
    
    # Verify train/valid images exist
    train_dir = dataset_dir / "train"
    valid_dir = dataset_dir / "valid"
    
    dataset_yaml = {
        "path": str(dataset_dir),
        "train": "train/images" if (train_dir / "images").exists() else "train",
        "val": "valid/images" if (valid_dir / "images").exists() else "valid",
        "nc": 1,
        "names": ["drone"]
    }
    with open(yaml_path, "w") as f:
        yaml.dump(dataset_yaml, f, default_flow_style=False)
    print(f"✅ Created/Updated drone dataset config at: {yaml_path}")
    return yaml_path, "drone_detection"

def main():
    print("=" * 60)
    print("      YOLO Training Optimizer for MacBook Apple Silicon (M2)")
    print("=" * 60)
    
    # 1. Select Dataset
    print("\n👉 Chọn Dataset muốn Train:")
    print("   [1] Aerial Traffic Dataset (dataset) - Phát hiện ô tô, xe máy từ trên cao (Khuyên dùng cho traffic sim)")
    print("   [2] Drone Detection Dataset (drone_dataset) - Phát hiện các thiết bị bay Drone")
    
    choice = input("Lựa chọn (1 hoặc 2, mặc định 1): ").strip()
    if choice == "2":
        yaml_path, project_name = setup_drone_yaml()
    else:
        yaml_path, project_name = setup_traffic_yaml()
        
    # 2. Select Model
    print("\n👉 Chọn Model YOLO nền tảng:")
    print("   [1] YOLO11s (yolo11s.pt) - Tốt nhất, khớp với bản yolo_enhanced đang chạy")
    print("   [2] YOLOv8s (yolov8s.pt) - Khá cân bằng")
    print("   [3] YOLOv8n (yolov8n.pt) - Rất nhẹ, train nhanh nhất")
    
    model_choice = input("Lựa chọn (1, 2, hoặc 3, mặc định 1): ").strip()
    if model_choice == "2":
        model_name = "yolov8s.pt"
    elif model_choice == "3":
        model_name = "yolov8n.pt"
    else:
        model_name = "yolo11s.pt"
        
    # 3. Enter Epochs
    epochs_input = input("\n👉 Nhập số Epochs muốn train (mặc định 50): ").strip()
    try:
        epochs = int(epochs_input) if epochs_input else 50
    except ValueError:
        epochs = 50
        
    # 4. Display optimization info
    print("\n🚀 Đang cấu hình huấn luyện tối ưu hóa cho chip Apple Silicon M2...")
    print(f"   • Device: GPU MPS (Metal Performance Shaders)")
    print(f"   • Cache: Enabled (Sử dụng bộ nhớ RAM hợp nhất UMA cực nhanh)")
    print(f"   • Workers: 4 (Tối ưu hóa đa luồng xử lý trên nhân CPU hiệu năng cao)")
    print(f"   • Batch: 16 (An toàn cho bộ nhớ Macbook Air)")
    print(f"   • Model gốc: {model_name}")
    print(f"   • Dataset: {yaml_path}")
    print(f"   • Epochs: {epochs}")
    print("=" * 60)
    
    # Load model
    model = YOLO(model_name)
    
    # Start train
    results = model.train(
        data=str(yaml_path),
        epochs=epochs,
        imgsz=640,
        batch=16,
        patience=10,
        device="mps",        # 🚀 Sử dụng GPU Metal của Apple
        cache=True,          # ⚡️ Cache ảnh vào RAM (Macbook UMA làm việc này siêu tốt)
        workers=4,           # 🧵 4 luồng CPU load data
        amp=True,            # 💎 Huấn luyện độ chính xác hỗn hợp giúp tăng tốc
        val=False,           # ⚡️ Tắt validation giữa các epoch để tránh lỗi NMS chậm trên Apple Silicon GPU (MPS)
        nms=False,           # 🚫 Vô hiệu hoá NMS để tránh cảnh báo thời gian giới hạn trên MPS
        resume=True,         # 🔁 Tiếp tục training từ checkpoint trước
        save=True,
        verbose=True,
        project=str(BASE_DIR / "runs"),
        name=project_name,
    )
    
    print("\n" + "=" * 60)
    print("✅ HUẤN LUYỆN HOÀN TẤT!")
    print(f"📁 Kết quả lưu tại: {BASE_DIR / 'runs' / project_name}")
    
    # Copy best model to base directory
    best_weights = BASE_DIR / "runs" / project_name / "weights" / "best.pt"
    if best_weights.exists():
        target_model_name = f"{model_name.replace('.pt', '')}_{project_name}_custom.pt"
        target_path = BASE_DIR / target_model_name
        shutil.copy(best_weights, target_path)
        print(f"💾 File weights tốt nhất đã được lưu ra ngoài: {target_path}")
        print(f"💡 Để sử dụng model này trong yolo_enhanced.py, hãy đổi: MODEL_PATH = \"{target_model_name}\"")
    print("=" * 60)

if __name__ == "__main__":
    main()
