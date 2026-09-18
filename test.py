from ultralytics import YOLOv10

model = YOLOv10(model="/root/autodl-tmp/Paperlab/yolov10-MNV4/runs/train/exp7/weights/best.pt")

if __name__ == '__main__':
    model.val(batch=8,
              imgsz=640,
              data='/root/autodl-tmp/Paperlab/yolov10-MNV4/PCB_remake.yaml',
              split="test")