from ultralytics.nn.Extramodule.ODConv import ODConv  # 假设你已经实现或安装了 ODConv 模块
import torch
import torchvision.transforms as T
import matplotlib.pyplot as plt
import numpy as np

# 示例输入（1 张 3 通道 RGB 图片）
x = torch.randn(1, 3, 224, 224)  # shape: [B, C_in, H, W]

# 定义 ODConv 模块
odconv = ODConv2d(in_channels=3, out_channels=16, kernel_size=3, padding=1)

# 得到 ODConv 输出
with torch.no_grad():
    out = odconv(x)  # 输出 shape: [1, 16, 224, 224]
    # 取第一个样本的第一个通道的特征图
    feature_map = out[0, 0, :, :].cpu().numpy()

    # 归一化到 [0,1] 区间以便显示
    feature_map -= feature_map.min()
    feature_map /= feature_map.max()

    # 显示特征图
    plt.imshow(feature_map, cmap='viridis')  # 或 'gray'
    plt.title("ODConv Output - Channel 0")
    plt.axis("off")
    plt.show()