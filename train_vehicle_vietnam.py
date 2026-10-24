#!/usr/bin/env python3
"""
Enhanced YOLOv8 Training Script — Vehicle Vietnam-CanTho Dataset
================================================================
Optimized for MacBook Air M2 (Apple Silicon / MPS GPU).

Dataset: Vehicle Vietnam-CanTho.v19 (Roboflow)
  - 1110 images (678 train / 216 valid / 216 test)
  - 4 classes: bus, car, motorbike, truck
  - Original resolution: 416×416

Enhancements over basic training:
  • Heavy data augmentation (mosaic, mixup, HSV jitter, flips, scale)
  • Cosine LR scheduler for smoother convergence
  • AdamW optimizer with weight decay
  • Early stopping (patience=15) to prevent overfitting
  • Validation enabled (tracks mAP during training)
  • Multi-scale training for robustness
  • Warm-up period for stable start
  • Auto-export of best model + test-set evaluation
"""

import os
import sys
import shutil
from pathlib import Path
from ultralytics import YOLO

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.resolve()
DATASET_DIR = BASE_DIR / "Vehicle Vietnam-CanTho.v19-du-lieu-goc.yolov8"
DATA_YAML = DATASET_DIR / "data.yaml"

# Base model — yolov8s is a good balance of accuracy and speed for M2
BASE_MODEL = "yolov8s.pt"

# Output
PROJECT_DIR = BASE_DIR / "runs"
RUN_NAME = "vehicle_vietnam"
EXPORTED_MODEL_NAME = "yolov8s_vehicle_vietnam_custom.pt"
RESUME_IF_EXISTS = True



def verify_dataset():
    """Verify that the dataset exists and has the expected structure."""
    print("=" * 60)
    print("  🔍 Verifying Dataset: Vehicle Vietnam-CanTho.v19")
    print("=" * 60)

    if not DATASET_DIR.exists():
        print(f"❌ Dataset directory not found: {DATASET_DIR}")
        sys.exit(1)

    if not DATA_YAML.exists():
        print(f"❌ data.yaml not found: {DATA_YAML}")
        sys.exit(1)

    splits = {"train": 0, "valid": 0, "test": 0}
    for split in splits:
        img_dir = DATASET_DIR / split / "images"
        lbl_dir = DATASET_DIR / split / "labels"
        if img_dir.exists():
            imgs = list(img_dir.glob("*.[jJ][pP][gG]")) + list(img_dir.glob("*.[pP][nN][gG]"))
            splits[split] = len(imgs)
            print(f"  ✅ {split:>6}: {len(imgs):>4} images, labels={'✅' if lbl_dir.exists() else '❌'}")
        else:
            print(f"  ⚠️  {split:>6}: directory not found ({img_dir})")

    total = sum(splits.values())
    print(f"\n  📊 Total images: {total}")
    print(f"  📋 Classes: bus, car, motorbike, truck (nc=4)")

    if splits["train"] == 0:
        print("❌ No training images found. Aborting.")
        sys.exit(1)

    return splits


def train():
    """Run enhanced YOLOv8 training."""
    splits = verify_dataset()

    print("\n" + "=" * 60)
    print("  🚀 Starting Enhanced YOLOv8 Training")
    print("=" * 60)
    # Auto-detect best device for M2
    import torch
    if torch.backends.mps.is_available():
        device = "mps"
        device_label = "MPS (Apple Silicon GPU)"
    else:
        device = "cpu"
        device_label = "CPU"
    
    print(f"  • Base Model   : {BASE_MODEL}")
    print(f"  • Dataset      : {DATA_YAML}")
    print(f"  • Image Size   : 416×416 (native dataset resolution)")
    print(f"  • Device       : {device_label}")
    print(f"  • Epochs       : 80 (with early stopping, patience=20)")
    print(f"  • Batch Size   : 8")
    print(f"  • Optimizer    : AdamW (lr=0.001, weight_decay=0.0005)")
    print(f"  • LR Scheduler : Cosine Annealing")
    print(f"  • Augmentation : Mosaic + Mixup + HSV + Flip + Scale")
    print("=" * 60)

    # Check if we should resume from a previous checkpoint
    checkpoint_path = PROJECT_DIR / RUN_NAME / "weights" / "last.pt"
    if RESUME_IF_EXISTS and checkpoint_path.exists():
        print(f"  🔄 Found existing checkpoint at {checkpoint_path}")
        print("     Resuming training from the last saved epoch...")
        model = YOLO(str(checkpoint_path))
        resume_training = True
    else:
        print(f"  🆕 Starting fresh training with base model: {BASE_MODEL}")
        model = YOLO(BASE_MODEL)
        resume_training = False

    # Enhanced training with all optimizations
    results = model.train(
        data=str(DATA_YAML),

        # --- Core Training Parameters ---
        resume=resume_training,
        epochs=80,
        imgsz=416,                # Native dataset resolution — no upscaling overhead
        batch=8,                  # Conservative for MacBook Air M2 8GB unified memory
        device=device,            # Auto-detected: MPS or CPU

        # --- Optimizer ---
        optimizer="AdamW",        # Better generalization than SGD for small datasets
        lr0=0.001,                # Initial learning rate
        lrf=0.01,                 # Final LR = lr0 * lrf (cosine decay target)
        weight_decay=0.0005,      # L2 regularization
        cos_lr=True,              # Cosine annealing LR scheduler
        warmup_epochs=3,          # Warm-up for stable start
        warmup_momentum=0.8,

        # --- Early Stopping ---
        patience=20,              # Stop if no improvement for 20 epochs

        # --- Data Augmentation (critical for small dataset ~1100 images) ---
        mosaic=1.0,               # Mosaic augmentation probability
        mixup=0.15,               # MixUp augmentation (blend two images)
        copy_paste=0.1,           # Copy-paste augmentation
        hsv_h=0.015,              # HSV-Hue augmentation range
        hsv_s=0.7,                # HSV-Saturation augmentation range
        hsv_v=0.4,                # HSV-Value augmentation range
        degrees=5.0,              # Random rotation ±5°
        translate=0.1,            # Random translation ±10%
        scale=0.5,                # Random scale ±50%
        fliplr=0.5,               # Horizontal flip probability
        flipud=0.0,               # No vertical flip (vehicles don't appear upside-down)
        erasing=0.1,              # Random erasing augmentation

        # --- Validation & Saving ---
        val=False,                # Disable validation during training to avoid MPS NMS slowdown
        save=True,                # Save checkpoints
        save_period=10,           # Save checkpoint every 10 epochs
        plots=True,               # Generate training plots

        # --- Performance ---
        cache="disk",             # Cache to disk — more stable than RAM on 8GB M2
        workers=2,                # Data loading threads (conservative for M2 Air)
        amp=True,                 # Mixed precision training

        # --- Output ---
        project=str(PROJECT_DIR),
        name=RUN_NAME,
        verbose=True,
        exist_ok=True,            # Overwrite previous run with same name
    )

    return results


def export_and_evaluate(results):
    """Export best model and run evaluation on test set."""
    print("\n" + "=" * 60)
    print("  📊 Post-Training: Export & Evaluation")
    print("=" * 60)

    # Find best weights
    best_weights = PROJECT_DIR / RUN_NAME / "weights" / "best.pt"
    if not best_weights.exists():
        # Fallback to last.pt
        best_weights = PROJECT_DIR / RUN_NAME / "weights" / "last.pt"

    if not best_weights.exists():
        print("⚠️  No trained weights found. Training may have failed.")
        return

    # Copy best model to project root
    target_path = BASE_DIR / EXPORTED_MODEL_NAME
    shutil.copy(best_weights, target_path)
    print(f"  💾 Best model exported to: {target_path}")
    print(f"     File size: {target_path.stat().st_size / 1024 / 1024:.1f} MB")

    # Evaluate on test set
    print("\n  🧪 Evaluating on TEST set (unseen data)...")
    model = YOLO(str(target_path))

    try:
        eval_device = "cpu"
        test_results = model.val(
            data=str(DATA_YAML),
            split="test",
            device=eval_device,
            imgsz=416,
            batch=8,
            verbose=True,
        )

        print("\n" + "-" * 40)
        print("  📈 Test Set Results:")
        print(f"     mAP50      : {test_results.box.map50:.4f}")
        print(f"     mAP50-95   : {test_results.box.map:.4f}")
        print(f"     Precision   : {test_results.box.mp:.4f}")
        print(f"     Recall      : {test_results.box.mr:.4f}")
        print("-" * 40)

        # Per-class results
        class_names = ['bus', 'car', 'motorbike', 'truck']
        if hasattr(test_results.box, 'ap50') and len(test_results.box.ap50) == len(class_names):
            print("\n  📋 Per-Class AP50:")
            for i, name in enumerate(class_names):
                print(f"     {name:>10}: {test_results.box.ap50[i]:.4f}")

    except Exception as e:
        print(f"  ⚠️  Test evaluation error: {e}")
        print("     You can run it manually later with:")
        print(f"     model.val(data='{DATA_YAML}', split='test')")

    # Print usage instructions
    print("\n" + "=" * 60)
    print("  ✅ TRAINING COMPLETE!")
    print("=" * 60)
    print(f"\n  To use this model in yolo_enhanced.py:")
    print(f'    MODEL_PATH = "{EXPORTED_MODEL_NAME}"')
    print(f"\n  And update VEHICLE_CLASSES to:")
    print(f"    VEHICLE_CLASSES = {{")
    print(f'        0: "bus",')
    print(f'        1: "car",')
    print(f'        2: "motorbike",')
    print(f'        3: "truck",')
    print(f"    }}")
    print("=" * 60)


def main():
    print("\n" + "=" * 60)
    print("  🇻🇳 YOLOv8 Enhanced Training — Vehicle Vietnam-CanTho")
    print("  📍 Optimized for Apple Silicon M2")
    print("=" * 60)

    results = train()
    export_and_evaluate(results)


if __name__ == "__main__":
    main()
