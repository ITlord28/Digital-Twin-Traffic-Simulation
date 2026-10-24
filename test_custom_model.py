#!/usr/bin/env python3
"""
Test custom model on camera
"""

import cv2
from ultralytics import YOLO

# Load custom model
model_path = "yolov8_aerial_custom.pt"
model = YOLO(model_path)

CLASS_NAMES = {0: "car", 1: "motorcycle", 2: "bus", 3: "truck"}
COLORS = {0: (0, 255, 100), 1: (0, 200, 255), 2: (255, 150, 0), 3: (100, 100, 255)}

# Open webcam
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("❌ Cannot open camera")
    exit()

print("✅ Camera ready - Press 'q' to quit")
print(f"🤖 Using model: {model_path}")

while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    # Detect
    results = model(frame, conf=0.4, verbose=False)
    
    # Draw
    for r in results:
        for box in r.boxes:
            cls_id = int(box.cls[0])
            conf = box.conf[0].item()
            
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            label = CLASS_NAMES.get(cls_id, "unknown")
            color = COLORS.get(cls_id, (0, 255, 0))
            
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            text = f"{label}: {conf:.2f}"
            cv2.putText(frame, text, (x1, y1 - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    
    cv2.imshow("Aerial Traffic Detection", frame)
    
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
print("✅ Done")
