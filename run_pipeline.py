#!/usr/bin/env python3
"""
Complete pipeline: Extract → Label → Train → Done
"""

import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
SCRIPTS = [
    ("prepare_dataset.py", "📊 Preparing dataset..."),
    ("train_model.py", "🚀 Training model..."),
]

print("=" * 60)
print("🎯 YOLO Aerial Traffic - Complete Training Pipeline")
print("=" * 60)

for script, msg in SCRIPTS:
    script_path = BASE_DIR / script
    print(f"\n{msg}")
    print(f"📝 Running: {script}")
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=BASE_DIR,
            check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"❌ Error in {script}: {e}")
        sys.exit(1)

print("\n" + "=" * 60)
print("✅ Pipeline complete!")
print("=" * 60)
print("\n📌 Next steps:")
print("   1. Run test_custom_model.py to test on camera")
print("   2. Or use yolov8_aerial_custom.pt in your code")
print("\n💡 Custom model location: yolov8_aerial_custom.pt")
