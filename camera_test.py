#!/usr/bin/env python3
"""
Simple real-time camera detection with YOLOv8
Lightweight test script - press 'q' to quit
"""

import cv2
from ultralytics import YOLO

# Load model
model = YOLO("yolov8n.pt")

# Open webcam (0 = default camera)
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("❌ Không thể mở camera")
    exit()

print("✅ Camera đã mở - nhấn 'q' để thoát")

# Vehicle classes to detect
VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}

while True:
    ret, frame = cap.read()
    
    if not ret:
        print("❌ Không đọc được frame")
        break
    
    # Run detection
    results = model(frame, conf=0.4, verbose=False)
    
    # Draw boxes
    for r in results:
        for box in r.boxes:
            cls_id = int(box.cls[0])
            conf = box.conf[0].item()
            
            if cls_id in VEHICLE_CLASSES:
                label = VEHICLE_CLASSES[cls_id]
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                
                # Draw rectangle
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                
                # Draw label
                text = f"{label}: {conf:.2f}"
                cv2.putText(frame, text, (x1, y1 - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    
    # Show frame
    cv2.imshow("YOLOv8 Camera Detection", frame)
    
    # Press 'q' to exit
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
print("✅ Đã thoát")
