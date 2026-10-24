#!/usr/bin/env python3
"""
Extract frames từ video + Auto-label = Training Dataset
"""

import os
import cv2
import numpy as np
from pathlib import Path
from ultralytics import YOLO
from tqdm import tqdm

# Setup
BASE_DIR = Path(__file__).parent
DATASET_DIR = BASE_DIR / "dataset"
IMAGES_DIR = DATASET_DIR / "images"
LABELS_DIR = DATASET_DIR / "labels"

MODEL = YOLO("yolov8n.pt")
VEHICLE_CLASSES = {2: 0, 3: 1, 5: 2, 7: 3}  # class_id -> dataset_id
CLASS_NAMES = {0: "car", 1: "motorcycle", 2: "bus", 3: "truck"}

# Extract every N frames
FRAME_STEP = 5
CONF_THRESHOLD = 0.4

# Create folders
for folder in [IMAGES_DIR, LABELS_DIR]:
    folder.mkdir(parents=True, exist_ok=True)

# Use only 2 videos for quick training: smallest real + 2D screen
videos = [
    BASE_DIR / "intersection_1_vehicles.mp4",  # 239M - thực tế
    BASE_DIR / "Screen Recording 2026-05-26 at 14.58.08.mov",  # 73M - 2D
]
print(f"🎬 Found {len(videos)} videos (quick train mode)")

frame_count = 0

for video_path in videos:
    print(f"\n📹 Processing: {video_path.name}")
    
    cap = cv2.VideoCapture(str(video_path))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_id = 0
    extracted = 0
    
    pbar = tqdm(total=total_frames, desc=video_path.stem)
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        # Extract every N frames
        if frame_id % FRAME_STEP == 0:
            # Save image
            img_name = f"frame_{frame_count:05d}.jpg"
            img_path = IMAGES_DIR / img_name
            cv2.imwrite(str(img_path), frame)
            
            # Detect
            results = MODEL(frame, conf=CONF_THRESHOLD, verbose=False)
            
            # Save labels
            labels = []
            h, w = frame.shape[:2]
            
            for r in results:
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    if cls_id in VEHICLE_CLASSES:
                        dataset_cls = VEHICLE_CLASSES[cls_id]
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        
                        # Convert to YOLO format (center_x, center_y, width, height) normalized
                        cx = (x1 + x2) / 2 / w
                        cy = (y1 + y2) / 2 / h
                        bw = (x2 - x1) / w
                        bh = (y2 - y1) / h
                        
                        labels.append(f"{dataset_cls} {cx} {cy} {bw} {bh}")
            
            # Write labels
            label_path = LABELS_DIR / f"frame_{frame_count:05d}.txt"
            with open(label_path, "w") as f:
                for label in labels:
                    f.write(label + "\n")
            
            frame_count += 1
            extracted += 1
        
        frame_id += 1
        pbar.update(1)
    
    pbar.close()
    cap.release()
    print(f"✅ Extracted {extracted} frames")

print(f"\n📊 Total frames: {frame_count}")
print(f"📁 Dataset saved to: {DATASET_DIR}")
print("\n📋 Class mapping:")
for cid, name in CLASS_NAMES.items():
    print(f"  {cid}: {name}")
