#!/usr/bin/env python3
"""
MLX90640ESF BAA Thermal Camera - Direct Display
Shows live thermal image directly on Raspberry Pi screen
"""

import board
import busio
import adafruit_mlx90640
import numpy as np
import cv2
import time

print("=" * 50)
print("MLX90640ESF BAA Thermal Camera Display")
print("=" * 50)

# Initialize I2C
print("Initializing camera...")
i2c = busio.I2C(board.SCL, board.SDA)

# Initialize MLX90640
mlx = adafruit_mlx90640.MLX90640(i2c)

# CRITICAL: BAA version MUST use 2Hz refresh rate
mlx.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_2_HZ
print("✅ Camera initialized (2Hz refresh rate for BAA)")

# Create window
cv2.namedWindow("Thermal Camera - Thesis Project", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Thermal Camera - Thesis Project", 800, 600)

# Frame buffer (24x32 = 768 pixels)
frame = [0] * 768

print("\n" + "=" * 50)
print("DISPLAY RUNNING")
print("Controls:")
print("  'q' or ESC - Quit")
print("  's'         - Save screenshot")
print("  'c'         - Change color map")
print("=" * 50 + "\n")

# Color map options (removed GRAYSCALE which was causing the error)
color_maps = {
    0: cv2.COLORMAP_INFERNO,
    1: cv2.COLORMAP_JET,
    2: cv2.COLORMAP_HOT,
    3: cv2.COLORMAP_COOL,
    4: cv2.COLORMAP_RAINBOW
}
current_cmap = 0
color_map_names = {
    0: "INFERNO",
    1: "JET",
    2: "HOT",
    3: "COOL",
    4: "RAINBOW"
}

screenshot_count = 0

try:
    while True:
        # Get thermal data
        mlx.getFrame(frame)
        thermal = np.array(frame).reshape(24, 32)
        
        # Calculate temperatures
        min_temp = np.min(thermal)
        max_temp = np.max(thermal)
        avg_temp = np.mean(thermal)
        center_temp = thermal[12, 16]
        
        # Normalize to 0-255 for display
        if max_temp - min_temp > 0:
            normalized = (thermal - min_temp) / (max_temp - min_temp) * 255
        else:
            normalized = np.zeros_like(thermal)
        
        normalized = normalized.astype(np.uint8)
        
        # Apply selected color map
        colored = cv2.applyColorMap(normalized, color_maps[current_cmap])
        
        # Resize to larger size for better viewing
        display = cv2.resize(colored, (640, 480), interpolation=cv2.INTER_LINEAR)
        
        # Add temperature information overlay
        overlay = display.copy()
        
        # Semi-transparent background for text
        cv2.rectangle(overlay, (5, 5), (250, 130), (0, 0, 0), -1)
        display = cv2.addWeighted(display, 0.7, overlay, 0.3, 0)
        
        # Text colors
        text_color = (255, 255, 255)
        
        # Display temperatures
        cv2.putText(display, f"Min: {min_temp:.1f}C", (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, text_color, 2)
        cv2.putText(display, f"Max: {max_temp:.1f}C", (10, 55), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, text_color, 2)
        cv2.putText(display, f"Avg: {avg_temp:.1f}C", (10, 80), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, text_color, 2)
        cv2.putText(display, f"Center: {center_temp:.1f}C", (10, 105), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, text_color, 2)
        
        # Display color map info
        cv2.putText(display, f"Color Map: {color_map_names[current_cmap]}", (10, 440), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        # Display instructions
        cv2.putText(display, "Press 'q' to quit | 's' save | 'c' change color", (10, 465), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        # Show the image
        cv2.imshow("Thermal Camera - Thesis Project", display)
        
        # Handle keyboard input
        key = cv2.waitKey(1) & 0xFF
        
        if key == ord('q') or key == 27:  # 'q' or ESC
            break
        elif key == ord('s'):
            screenshot_count += 1
            filename = f"thermal_screenshot_{screenshot_count}.png"
            cv2.imwrite(filename, display)
            print(f"📸 Screenshot saved: {filename}")
        elif key == ord('c'):
            current_cmap = (current_cmap + 1) % len(color_maps)
            print(f"🎨 Color map changed to: {color_map_names[current_cmap]}")
            
except KeyboardInterrupt:
    print("\nInterrupted by user")
except Exception as e:
    print(f"Error: {e}")
finally:
    cv2.destroyAllWindows()
    print("\nDisplay closed.")
