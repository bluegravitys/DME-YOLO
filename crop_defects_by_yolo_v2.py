#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按 YOLO 标签逐目标裁剪缺陷，并保存回填所需元数据。
支持以下两类目录名，且会自动识别：
- image / label
- images / labels

输入示例:
dataset_root/
├── train/
│   ├── image/ 或 images/
│   └── label/ 或 labels/
├── val/
└── test/

输出示例:
output_root/
├── crops/
│   ├── train/
│   ├── val/
│   └── test/
└── metadata/
    ├── manifest.csv
    └── summary.json
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from PIL import Image

IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff")


@dataclass
class ObjectRecord:
    split: str
    image_dirname: str
    label_dirname: str
    image_stem: str
    image_relpath: str
    label_relpath: str
    class_id: int
    object_index: int
    crop_relpath: str
    img_width: int
    img_height: int
    x1: int
    y1: int
    x2: int
    y2: int
    box_width: int
    box_height: int
    cx_norm: float
    cy_norm: float
    w_norm: float
    h_norm: float
    padding_ratio: float


def resolve_split_dirs(split_dir: Path) -> Tuple[Path, Path, str, str]:
    image_candidates = ["image", "images"]
    label_candidates = ["label", "labels"]

    img_dir = None
    lbl_dir = None
    img_name = None
    lbl_name = None

    for name in image_candidates:
        p = split_dir / name
        if p.exists() and p.is_dir():
            img_dir = p
            img_name = name
            break

    for name in label_candidates:
        p = split_dir / name
        if p.exists() and p.is_dir():
            lbl_dir = p
            lbl_name = name
            break

    if img_dir is None:
        raise FileNotFoundError(f"未找到图像目录（image/images）: {split_dir}")
    if lbl_dir is None:
        raise FileNotFoundError(f"未找到标签目录（label/labels）: {split_dir}")

    return img_dir, lbl_dir, img_name, lbl_name


def find_image_for_label(images_dir: Path, stem: str) -> Optional[Path]:
    for ext in IMG_EXTS:
        candidate = images_dir / f"{stem}{ext}"
        if candidate.exists():
            return candidate
    return None


def parse_label_line(line: str) -> Optional[Tuple[int, float, float, float, float]]:
    parts = line.strip().split()
    if not parts:
        return None
    if len(parts) < 5:
        raise ValueError(f"标签行列数不足 5 列: {line!r}")
    class_id = int(float(parts[0]))
    cx, cy, w, h = map(float, parts[1:5])
    return class_id, cx, cy, w, h


def yolo_to_xyxy(cx: float, cy: float, w: float, h: float, img_w: int, img_h: int, padding_ratio: float = 0.0):
    bw = w * img_w
    bh = h * img_h
    pad_w = bw * padding_ratio
    pad_h = bh * padding_ratio

    x1 = int(round(cx * img_w - bw / 2 - pad_w))
    y1 = int(round(cy * img_h - bh / 2 - pad_h))
    x2 = int(round(cx * img_w + bw / 2 + pad_w))
    y2 = int(round(cy * img_h + bh / 2 + pad_h))

    x1 = max(0, min(x1, img_w - 1))
    y1 = max(0, min(y1, img_h - 1))
    x2 = max(1, min(x2, img_w))
    y2 = max(1, min(y2, img_h))

    if x2 <= x1:
        x2 = min(img_w, x1 + 1)
    if y2 <= y1:
        y2 = min(img_h, y1 + 1)

    return x1, y1, x2, y2


def iter_label_files(labels_dir: Path) -> Iterable[Path]:
    return sorted(labels_dir.glob("*.txt")) if labels_dir.exists() else []


def ensure_dirs(base_output: Path, splits: Sequence[str]) -> None:
    (base_output / "crops").mkdir(parents=True, exist_ok=True)
    (base_output / "metadata").mkdir(parents=True, exist_ok=True)
    for split in splits:
        (base_output / "crops" / split).mkdir(parents=True, exist_ok=True)


def save_manifest(records: List[ObjectRecord], output_root: Path) -> None:
    metadata_dir = output_root / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)

    manifest_csv = metadata_dir / "manifest.csv"
    fieldnames = list(asdict(records[0]).keys()) if records else list(ObjectRecord.__annotations__.keys())

    with open(manifest_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rec in records:
            writer.writerow(asdict(rec))

    summary = {"total_objects": len(records), "splits": {}}
    for rec in records:
        summary["splits"].setdefault(rec.split, 0)
        summary["splits"][rec.split] += 1

    with open(metadata_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


def process_split(dataset_root: Path, output_root: Path, split: str, padding_ratio: float) -> List[ObjectRecord]:
    split_dir = dataset_root / split
    if not split_dir.exists():
        print(f"[Warning] 跳过 split={split}，未找到目录: {split_dir}")
        return []

    try:
        images_dir, labels_dir, image_dirname, label_dirname = resolve_split_dirs(split_dir)
    except Exception as exc:
        print(f"[Warning] 跳过 split={split}: {exc}")
        return []

    records: List[ObjectRecord] = []

    for label_path in iter_label_files(labels_dir):
        image_stem = label_path.stem
        image_path = find_image_for_label(images_dir, image_stem)
        if image_path is None:
            print(f"[Warning] 未找到对应图像: {label_path}")
            continue

        try:
            image = Image.open(image_path).convert("RGB")
        except Exception as exc:
            print(f"[Warning] 读取图像失败 {image_path}: {exc}")
            continue

        img_w, img_h = image.size
        with open(label_path, "r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f.readlines() if ln.strip()]

        if not lines:
            continue

        for obj_idx, line in enumerate(lines):
            parsed = parse_label_line(line)
            if parsed is None:
                continue

            class_id, cx, cy, w, h = parsed
            x1, y1, x2, y2 = yolo_to_xyxy(cx, cy, w, h, img_w, img_h, padding_ratio)
            crop = image.crop((x1, y1, x2, y2))

            crop_relpath = Path(
                "crops", split, f"class_{class_id}",
                f"{image_stem}__obj{obj_idx:03d}__cls{class_id}.png"
            )
            crop_abspath = output_root / crop_relpath
            crop_abspath.parent.mkdir(parents=True, exist_ok=True)
            crop.save(crop_abspath)

            records.append(ObjectRecord(
                split=split,
                image_dirname=image_dirname,
                label_dirname=label_dirname,
                image_stem=image_stem,
                image_relpath=str(Path(split, image_dirname, image_path.name)).replace("\\", "/"),
                label_relpath=str(Path(split, label_dirname, label_path.name)).replace("\\", "/"),
                class_id=class_id,
                object_index=obj_idx,
                crop_relpath=str(crop_relpath).replace("\\", "/"),
                img_width=img_w,
                img_height=img_h,
                x1=x1, y1=y1, x2=x2, y2=y2,
                box_width=x2 - x1,
                box_height=y2 - y1,
                cx_norm=cx, cy_norm=cy, w_norm=w, h_norm=h,
                padding_ratio=padding_ratio,
            ))

    return records


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="按 YOLO 标签裁剪所有目标，并生成回填所需元数据。")
    parser.add_argument("--dataset_root", type=Path, required=True, help="原始数据集根目录")
    parser.add_argument("--output_root", type=Path, required=True, help="裁剪输出根目录")
    parser.add_argument("--splits", nargs="+", default=["train", "val", "test"], help="要处理的 split 列表")
    parser.add_argument("--padding_ratio", type=float, default=0.0, help="检测框额外扩展比例，例如 0.1")
    return parser


def main() -> None:
    parser = build_argparser()
    args = parser.parse_args()

    ensure_dirs(args.output_root, args.splits)
    all_records: List[ObjectRecord] = []

    for split in args.splits:
        split_records = process_split(args.dataset_root, args.output_root, split, args.padding_ratio)
        print(f"[Info] split={split}, 裁剪目标数={len(split_records)}")
        all_records.extend(split_records)

    save_manifest(all_records, args.output_root)
    print(f"[Done] 总裁剪目标数={len(all_records)}")
    print(f"[Done] 清单文件: {args.output_root / 'metadata' / 'manifest.csv'}")


if __name__ == "__main__":
    main()
