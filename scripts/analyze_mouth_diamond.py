#!/usr/bin/env python3
"""Analiza el solape entre la máscara de boca y el recorte tipo diamante.

Replica la lógica relevante de backend/avatar_app/app.js para cuantificar cuánto
área de la zona de boca queda descartada por el diamante.
"""

from __future__ import annotations

import argparse
import math


def smoothstep(edge0: float, edge1: float, x: float) -> float:
    if edge0 == edge1:
        return 0.0
    t = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def mouth_weight(x: float, y: float, center_x: float, center_y: float, width: float, height: float, curve: float) -> float:
    dx = x - center_x
    ax = abs(dx)
    if ax > width:
        return 0.0
    norm_x = dx / width
    curve_y = center_y - curve * norm_x * norm_x
    dy = y - curve_y
    ay = abs(dy)
    if ay > height:
        return 0.0
    wx = 1.0 - ax / width
    wy = 1.0 - ay / height
    return max(0.0, min(1.0, wx * wy))


def mouth_overlay_mix(w: float) -> float:
    rim = smoothstep(0.26, 0.46, w) * (1.0 - smoothstep(0.68, 0.84, w))
    inner_tiny = smoothstep(0.70, 0.82, w) * 0.22
    return max(0.0, min(1.0, rim + inner_tiny))


def diamond_inside(x: float, y: float, cx: float, cy: float, rx: float, ry: float, rot: float) -> bool:
    c = math.cos(rot)
    s = math.sin(rot)
    local_x = c * (x - cx) + s * (y - cy)
    local_y = -s * (x - cx) + c * (y - cy)
    field = abs(local_x) / max(1e-5, abs(rx)) + abs(local_y) / max(1e-5, abs(ry))
    return field <= 1.0


def run_case(rx: float, ry: float, label: str) -> None:
    center_x = -0.045
    center_y = 0.16
    width = 0.18
    height = 0.14
    curve = 0.0
    rot = 0.0

    total_mouth = 0
    cut_mouth = 0
    inner_total = 0
    inner_cut = 0
    overlay_low_inside = 0
    inside_diamond = 0

    nx = 801
    ny = 601
    for ix in range(nx):
        x = (center_x - width) + (2.0 * width) * (ix / (nx - 1))
        for iy in range(ny):
            y = (center_y - height) + (2.0 * height) * (iy / (ny - 1))
            w = mouth_weight(x, y, center_x, center_y, width, height, curve)
            if w <= 0.0:
                continue
            total_mouth += 1
            inside = diamond_inside(x, y, center_x, center_y, rx, ry, rot)
            if inside:
                cut_mouth += 1
                inside_diamond += 1
                if mouth_overlay_mix(w) <= 0.08:
                    overlay_low_inside += 1
            if w > 0.70:
                inner_total += 1
                if inside:
                    inner_cut += 1

    print(f"[{label}] rx={rx:.3f} ry={ry:.3f}")
    print(f"  cut_mouth_frac={cut_mouth / max(1, total_mouth):.4f}")
    print(f"  cut_inner_frac={inner_cut / max(1, inner_total):.4f}")
    print(f"  low_overlay_inside_frac={overlay_low_inside / max(1, inside_diamond):.4f}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--small-rx", type=float, default=0.06)
    parser.add_argument("--small-ry", type=float, default=0.035)
    args = parser.parse_args()

    run_case(0.11, 0.07, "default")
    run_case(args.small_rx, args.small_ry, "smaller")


if __name__ == "__main__":
    main()
