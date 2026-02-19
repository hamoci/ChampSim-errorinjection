#!/usr/bin/env python3
"""
Page Retirement Limit Analysis for 32GB DRAM
Shows how many page retirements are needed to exhaust memory for 4KB and 2MB pages.
"""

import os
import numpy as np
import matplotlib.pyplot as plt

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = SCRIPT_DIR

# Constants
DRAM_SIZE_GB = 32
DRAM_SIZE_BYTES = DRAM_SIZE_GB * 1024 * 1024 * 1024  # 32GB in bytes

PAGE_4KB = 4 * 1024          # 4KB = 4,096 bytes
PAGE_2MB = 2 * 1024 * 1024   # 2MB = 2,097,152 bytes

# Calculate total pages
TOTAL_4KB_PAGES = DRAM_SIZE_BYTES // PAGE_4KB  # 8,388,608 pages
TOTAL_2MB_PAGES = DRAM_SIZE_BYTES // PAGE_2MB  # 16,384 pages

# Color scheme (matching hugepage_IPC_comparison.py)
color_4kb = '#EE5A6F'  # Red/Pink
color_2mb = '#4A90E2'  # Blue

def main():
    print(f"=== 32GB DRAM Page Retirement Limit Analysis ===")
    print(f"DRAM Size: {DRAM_SIZE_GB}GB ({DRAM_SIZE_BYTES:,} bytes)")
    print(f"4KB Page: {PAGE_4KB:,} bytes -> Total {TOTAL_4KB_PAGES:,} pages")
    print(f"2MB Page: {PAGE_2MB:,} bytes -> Total {TOTAL_2MB_PAGES:,} pages")
    print(f"Ratio: {TOTAL_4KB_PAGES / TOTAL_2MB_PAGES:.0f}x more 4KB pages than 2MB pages")

    # Create figure with single plot
    fig, ax = plt.subplots(figsize=(6, 4))

    # Create percentage-based x-axis (0% to 100% of pages retired)
    percentages = np.linspace(0, 100, 101)

    # Calculate actual number of retirements at each percentage
    retirements_4kb = (percentages / 100) * TOTAL_4KB_PAGES
    retirements_2mb = (percentages / 100) * TOTAL_2MB_PAGES

    ax.plot(percentages, retirements_4kb, color=color_4kb, linewidth=2.5, label='4KB Page', marker='o', markersize=3, markevery=10)
    ax.plot(percentages, retirements_2mb, color=color_2mb, linewidth=2.5, label='2MB Page', marker='s', markersize=3, markevery=10)

    ax.set_xlabel('Memory Capacity Lost (%)', fontsize=10)
    ax.set_ylabel('Page Retirements (log scale)', fontsize=10)
    ax.set_yscale('log')
    ax.tick_params(axis='both', labelsize=9)
    ax.legend(loc='lower right', fontsize=9, framealpha=0.9)
    ax.grid(True, linestyle='--', alpha=0.5, linewidth=0.5)
    ax.set_xlim(0, 100)
    ax.set_ylim(1e2, 1e7)

    # Add annotations for 25%, 50%, 75%, 100% points
    annotation_points = [25, 50, 75, 100]

    for pct in annotation_points:
        val_4kb = int((pct / 100) * TOTAL_4KB_PAGES)
        val_2mb = int((pct / 100) * TOTAL_2MB_PAGES)

        # 4KB annotation (above the line)
        ax.annotate(f'{val_4kb:,}', xy=(pct, val_4kb), xytext=(pct - 8, val_4kb * 2.5),
                    fontsize=7, fontweight='bold', color=color_4kb,
                    arrowprops=dict(arrowstyle='->', color=color_4kb, lw=0.8))

        # 2MB annotation (below the line)
        ax.annotate(f'{val_2mb:,}', xy=(pct, val_2mb), xytext=(pct - 8, val_2mb / 2.5),
                    fontsize=7, fontweight='bold', color=color_2mb,
                    arrowprops=dict(arrowstyle='->', color=color_2mb, lw=0.8))

    plt.tight_layout(pad=0.5)

    # Save plot
    png_path = os.path.join(OUTPUT_DIR, "pageretirement_limit.png")
    plt.savefig(png_path, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    print(f"\nPNG saved to: {png_path}")

    plt.close()

    # Print summary
    print(f"\n=== Summary ===")
    print(f"4KB Page: {TOTAL_4KB_PAGES:,} retirements to exhaust 32GB")
    print(f"2MB Page: {TOTAL_2MB_PAGES:,} retirements to exhaust 32GB")
    print(f"4KB pages require {TOTAL_4KB_PAGES // TOTAL_2MB_PAGES}x more retirements than 2MB pages")

if __name__ == "__main__":
    main()
