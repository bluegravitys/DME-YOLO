
from ultralytics import YOLO

# Train the model
results = model.train(task='segment',
                      data="/root/autodl-tmp/yolov10-MNV4/seg.yaml",
                      model='/root/autodl-tmp/yolov10-MNV4/yolov8m-seg.pt',
                      epochs=300,
                      imgsz=2048,
                      batch=16,
                      workers=0,
                      save_period=10,  # 多少轮保存一个模型（-1 不保存）
                      resume=False,
                      overlap_mask=True,
                      mask_ratio=4,
                      optimizer="SGD",
                      cache=false)
