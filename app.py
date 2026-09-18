import base64
import io
import logging
import socket
import sys
import threading
import time
import webbrowser
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image, UnidentifiedImageError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.FileHandler(Path(__file__).resolve().parent / 'app_server.log', encoding='utf-8')],
    force=False,
)

def get_runtime_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


ROOT = get_runtime_root()
STATIC_DIR = ROOT / "static"
TEMPLATES_DIR = ROOT / "templates"
DEFAULT_MODEL_PATH = ROOT / "best.pt"
DEFAULT_CLASSES_PATH = ROOT / "classes.txt"

CLASS_TRANSLATIONS = {
    "missing_hole": "缺孔",
    "mouse_bite": "鼠咬",
    "open_circuit": "断路",
    "short": "短路",
    "spur": "毛刺",
    "spurious_copper": "杂铜",
}

CLASS_DESCRIPTIONS = {
    "missing_hole": "钻孔缺失、孔壁不完整，可能影响安装与导通。",
    "mouse_bite": "板边被侵蚀或缺角，容易造成结构边缘异常。",
    "open_circuit": "走线断开，电流路径无法形成闭环。",
    "short": "相邻导线意外连通，存在明显短路风险。",
    "spur": "局部铜刺或尖锐突起，可能诱发电气毛刺。",
    "spurious_copper": "多余铜箔残留或异常附着，影响版面洁净度。",
}

CARD_COLORS = {
    "missing_hole": "#ff6b7d",
    "mouse_bite": "#ff935c",
    "open_circuit": "#f6bf58",
    "short": "#3ddc97",
    "spur": "#62c5ff",
    "spurious_copper": "#a78bfa",
}

EXAMPLES = {
    "missing_hole": {
        "title": "缺孔示例",
        "tag": "装配风险",
        "path": ROOT / "PCB_remake" / "test" / "images" / "01_missing_hole_04.jpg",
        "summary": "适合快速观察孔位缺失和孔壁异常。",
    },
    "mouse_bite": {
        "title": "鼠咬示例",
        "tag": "边缘异常",
        "path": ROOT / "PCB_remake" / "test" / "images" / "01_mouse_bite_12.jpg",
        "summary": "适合演示板边侵蚀、缺角和轮廓异常。",
    },
    "open_circuit": {
        "title": "断路示例",
        "tag": "导通失效",
        "path": ROOT / "PCB_remake" / "test" / "images" / "01_open_circuit_04_create_5.jpg",
        "summary": "适合展示关键走线断裂后的定位效果。",
    },
}


def load_class_names() -> list[str]:
    if DEFAULT_CLASSES_PATH.exists():
        return [line.strip() for line in DEFAULT_CLASSES_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    return list(CLASS_TRANSLATIONS.keys())


CLASS_NAMES = load_class_names()

DEFECT_LIBRARY = [
    {
        "key": defect_name,
        "name": CLASS_TRANSLATIONS.get(defect_name, defect_name),
        "description": CLASS_DESCRIPTIONS.get(defect_name, "常见 PCB 缺陷类型。"),
        "color": CARD_COLORS.get(defect_name, "#62c5ff"),
        "risk": {
            "missing_hole": "影响插装、导通和焊接稳定性。",
            "mouse_bite": "影响外形精度与局部强度。",
            "open_circuit": "直接导致功能失效。",
            "short": "可能烧毁器件或触发保护。",
            "spur": "容易形成误触点或高频干扰。",
            "spurious_copper": "会降低绝缘和清洁度。",
        }.get(defect_name, "建议进行人工复核。"),
        "inspection": {
            "missing_hole": "检查孔径、孔壁和周边焊盘。",
            "mouse_bite": "检查板边轮廓、切割工艺和缺口位置。",
            "open_circuit": "重点复核关键走线、过孔与焊盘连接。",
            "short": "复核相邻线距和焊盘桥连区域。",
            "spur": "检查尖角、飞边和局部残铜。",
            "spurious_copper": "检查残铜、异物和清洗工序。",
        }.get(defect_name, "根据工艺要求进行复核。"),
    }
    for defect_name in CLASS_NAMES
]


@lru_cache(maxsize=4)
def load_model(model_path: str) -> Any:
    from ultralytics import YOLOv10

    normalized_path = model_path.strip().strip('"').strip("'")
    resolved = Path(normalized_path).expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"未找到模型文件: {resolved}")
    if resolved.suffix.lower() != ".pt":
        raise ValueError("模型文件必须为 .pt 格式。")
    return YOLOv10(model=str(resolved))


def translate_class(name: str) -> str:
    return CLASS_TRANSLATIONS.get(name, name)


def detect_level(total: int) -> dict[str, str]:
    if total == 0:
        return {
            "label": "合格",
            "message": "当前图片未发现明显 PCB 缺陷，可作为通过样本继续复核。",
            "accent": "#3ddc97",
        }
    if total <= 2:
        return {
            "label": "轻微异常",
            "message": "检测到少量疑似缺陷，建议人工复核关键线路和孔位。",
            "accent": "#f6bf58",
        }
    return {
        "label": "高风险",
        "message": "当前样本存在多处缺陷，建议优先隔离并进行详细复检。",
        "accent": "#ff6b7d",
    }


def read_image_bytes(upload: UploadFile | None, example_name: str) -> tuple[bytes, str]:
    if upload and upload.filename:
        payload = upload.file.read()
        if not payload:
            raise ValueError("上传文件为空，请重新选择 PCB 图片。")
        return payload, upload.filename

    if example_name:
        example = EXAMPLES.get(example_name)
        if not example or not example["path"].exists():
            raise FileNotFoundError(f"示例图片不存在: {example_name}")
        return example["path"].read_bytes(), example["path"].name

    raise ValueError("请上传 PCB 图片，或先选择一个示例样本。")


def to_pil_image(payload: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(payload)).convert("RGB")
    except UnidentifiedImageError as exc:
        raise ValueError("无法识别图片格式，请上传 PNG、JPG 或 JPEG 文件。") from exc
    return image


def image_to_data_url(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def summarize_counts(counts: Counter[str], total: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    max_count = max(counts.values()) if counts else 1
    for defect_name in CLASS_NAMES:
        count = counts.get(defect_name, 0)
        items.append(
            {
                "key": defect_name,
                "name": translate_class(defect_name),
                "count": count,
                "ratio": 0 if total == 0 else round((count / total) * 100, 1),
                "width": 0 if max_count == 0 else round((count / max_count) * 100, 1),
                "color": CARD_COLORS.get(defect_name, "#62c5ff"),
            }
        )
    return items


def build_detection_payload(
    payload: bytes,
    source_name: str,
    model_path: str,
    image_size: int,
    conf_threshold: float,
    iou_threshold: float,
) -> dict[str, Any]:
    pil_image = to_pil_image(payload)
    model = load_model(model_path)

    started = time.perf_counter()
    results = model.predict(
        source=pil_image,
        imgsz=int(image_size),
        conf=float(conf_threshold),
        iou=float(iou_threshold),
        verbose=False,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000

    result = results[0]
    boxes = result.boxes
    counts: Counter[str] = Counter()
    details: list[dict[str, Any]] = []

    for index, box in enumerate(boxes):
        cls_id = int(box.cls[0].item())
        confidence = float(box.conf[0].item())
        label = CLASS_NAMES[cls_id] if cls_id < len(CLASS_NAMES) else str(cls_id)
        x1, y1, x2, y2 = [int(value) for value in box.xyxy[0].tolist()]
        counts[label] += 1
        details.append(
            {
                "index": index + 1,
                "name": translate_class(label),
                "confidence": round(confidence * 100, 2),
                "box": [x1, y1, x2, y2],
            }
        )

    plotted = result.plot(conf=True, line_width=3, font_size=16, pil=False, labels=True, boxes=True, probs=False)
    annotated = Image.fromarray(plotted[:, :, ::-1])
    total = sum(counts.values())
    level = detect_level(total)
    dominant_name = translate_class(counts.most_common(1)[0][0]) if total else "无缺陷"

    annotated_image = image_to_data_url(annotated)

    return {
        "success": True,
        "annotated_image": annotated_image,
        "annotated_image_url": annotated_image,
        "summary": {
            "total": total,
            "dominant_name": dominant_name,
            "runtime_ms": round(elapsed_ms, 1),
            "model_name": Path(model_path).name,
            "image_size": f"{pil_image.width} x {pil_image.height}",
            "distribution": summarize_counts(counts, total),
        },
        "details": details,
        "level": level,
        "severity": level,
        "source_name": source_name,
    }


def build_base_context(request: Request, active_page: str) -> dict[str, Any]:
    return {
        "request": request,
        "active_page": active_page,
        "nav_items": [
            {"key": "home", "label": "首页", "href": "/"},
            {"key": "detect", "label": "在线检测", "href": "/detect"},
            {"key": "defects", "label": "缺陷说明", "href": "/defects"},
            {"key": "about", "label": "关于系统", "href": "/about"},
        ],
        "examples": [
            {
                "key": key,
                "title": value["title"],
                "tag": value["tag"],
                "summary": value["summary"],
                "preview_url": f"/examples/{key}",
            }
            for key, value in EXAMPLES.items()
        ],
        "defect_library": DEFECT_LIBRARY,
    }


app = FastAPI(title="PCB Defect Studio", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.get("/", response_class=HTMLResponse)
def home_page(request: Request) -> HTMLResponse:
    context = build_base_context(request, "home")
    context.update(
        {
            "hero_metrics": [
                {"label": "缺陷类别", "value": f"{len(CLASS_NAMES)} 类"},
                {"label": "部署方式", "value": "本地 .pt 推理"},
                {"label": "页面结构", "value": "4 个独立页面"},
                {"label": "推荐模式", "value": "人工复核 + AI 初筛"},
            ],
            "feature_cards": [
                {
                    "title": "真正多页面结构",
                    "copy_text": "首页负责展示，检测页负责操作，说明页负责知识沉淀，页面职责清晰。",
                },
                {
                    "title": "保留本地模型能力",
                    "copy_text": "继续调用你训练好的 YOLO `.pt` 权重，不改变检测主流程。",
                },
                {
                    "title": "结果展示更像系统",
                    "copy_text": "输出风险等级、分布统计和缺陷坐标，而不是单纯一张标注图。",
                },
            ],
        }
    )
    return templates.TemplateResponse(request=request, name="index.html", context=context)


@app.get("/detect", response_class=HTMLResponse)
def detect_page(request: Request) -> HTMLResponse:
    context = build_base_context(request, "detect")
    context.update(
        {
            "default_model_path": str(DEFAULT_MODEL_PATH),
            "default_image_size": 960,
            "default_conf_threshold": 0.25,
            "default_iou_threshold": 0.45,
        }
    )
    return templates.TemplateResponse(request=request, name="detect.html", context=context)


@app.get("/defects", response_class=HTMLResponse)
def defects_page(request: Request) -> HTMLResponse:
    context = build_base_context(request, "defects")
    return templates.TemplateResponse(request=request, name="defects.html", context=context)


@app.get("/about", response_class=HTMLResponse)
def about_page(request: Request) -> HTMLResponse:
    context = build_base_context(request, "about")
    context.update(
        {
            "timeline": [
                "加载本地训练好的 `.pt` 权重文件",
                "接收 PCB 图片并执行 YOLO 推理",
                "生成标注图、缺陷统计和坐标明细",
                "交由人工进行风险复核和工艺判断",
            ]
        }
    )
    return templates.TemplateResponse(request=request, name="about.html", context=context)


@app.get("/examples/{example_name}")
def example_image(example_name: str) -> FileResponse:
    example = EXAMPLES.get(example_name)
    if not example or not example["path"].exists():
        raise HTTPException(status_code=404, detail="示例图片不存在")
    return FileResponse(example["path"])


@app.post("/api/detect")
async def detect_api(
    image: UploadFile | None = File(default=None),
    example_name: str = Form(default=""),
    model_path: str = Form(default=str(DEFAULT_MODEL_PATH)),
    image_size: int = Form(default=960),
    conf_threshold: float = Form(default=0.25),
    iou_threshold: float = Form(default=0.45),
) -> JSONResponse:
    try:
        payload, source_name = read_image_bytes(image, example_name)
        data = build_detection_payload(
            payload=payload,
            source_name=source_name,
            model_path=model_path,
            image_size=image_size,
            conf_threshold=conf_threshold,
            iou_threshold=iou_threshold,
        )
        logging.info("Detection completed successfully for %s with model %s", source_name, model_path)
        return JSONResponse(data)
    except FileNotFoundError as exc:
        logging.warning("Model file not found: %s", exc)
        return JSONResponse({"success": False, "error": str(exc), "message": str(exc)}, status_code=404)
    except ValueError as exc:
        logging.warning("Validation error during detection: %s", exc)
        return JSONResponse({"success": False, "error": str(exc), "message": str(exc)}, status_code=400)
    except Exception as exc:
        logging.exception("Detection failed")
        message = f"检测失败: {exc}"
        return JSONResponse({"success": False, "error": message, "message": message}, status_code=500)


def find_available_port(host: str = "127.0.0.1", start_port: int = 7860, end_port: int = 7999) -> int:
    for port in range(start_port, end_port + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if sock.connect_ex((host, port)) != 0:
                return port
    raise RuntimeError(f"未找到可用端口，范围: {start_port}-{end_port}")


def run_server(host: str = "127.0.0.1", port: int = 7860, open_browser: bool = True) -> None:
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://{host}:{port}")).start()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_server(host="127.0.0.1", port=7860, open_browser=True)

