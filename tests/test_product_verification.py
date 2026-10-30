#!/usr/bin/env python3
"""
Quick Standalone Diagnostic Tool for CartMate Product Verification.
Tests:
1. Camera Capture (Picamera2 / USB / Software fallback)
2. YOLOv8 Deep Learning Product Detection (using best.pt)
3. OpenCV QR Code Scanner & Cryptographic HMAC Verification
4. Snapshot Generation and Annotation in detections/ directory
"""

import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from integration.product_detection_service import ProductDetector

def main():
    print("==================================================")
    print("🔍 CartMate Product Verification Diagnostic Tool")
    print("==================================================")

    # Initialize Product Detector
    detector = ProductDetector(output_dir="detections", conf_thresh=0.35)

    shelf_id = sys.argv[1] if len(sys.argv) > 1 else "SHELF_B"
    section = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    target_items = [sys.argv[3]] if len(sys.argv) > 3 else ["cube", "bread", "tall_box"]

    print(f"\n🚀 Running 3-second live verification test on {shelf_id} (Section {section})...")
    print(f"🎯 Target items to verify: {target_items}")
    print("Hold a product or QR code in front of the camera now!\n")

    result = detector.inspect_shelf_and_section(
        shelf_id=shelf_id,
        section=section,
        target_items=target_items,
        duration_sec=3.0
    )

    print("📊 [Verification Results Summary]:")
    print(f"   - Target Matched     : {'✅ YES' if result['target_matched'] else '❌ NO'}")
    print(f"   - YOLO Detected Items: {len(result['detected_products'])}")
    for p in result['detected_products']:
        print(f"     • {p['class']} (Confidence: {p.get('confidence', 0)*100:.1f}%)")
    
    print(f"   - QR Codes Verified  : {len(result['verified_qr_codes'])}")
    for q in result['verified_qr_codes']:
        print(f"     • Unit: {q['unit_id']} -> Name: {q.get('name')} (Weight: {q.get('weight_g')}g)")

    if result.get('snapshot_image'):
        print(f"   - Saved Photo        : 🖼️ {result['snapshot_image']}")

    detector.close()
    print("\n✅ Test Completed.")

if __name__ == "__main__":
    main()
