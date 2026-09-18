# GNRI 相似样本生成(图生图 / 数据增强)

本目录是 [dvirsamuel/NewtonRaphsonInversion](https://github.com/dvirsamuel/NewtonRaphsonInversion)(ICLR 2025, GNRI)的完整源码,另加一个批量生成脚本 `generate_samples.py`。

## 用途

给**一张图** → 反演(牛顿-拉夫森)得到噪声潜变量 → 从该潜变量**重生出一批相似但略有差异的样本**(改随机种子 / 改提示词)。这是图生图编辑 / 数据增强,不是文生图。

## 快速开始

```bash
# 1) 安装依赖(需要 NVIDIA 显卡 + CUDA)
pip install -r requirements.txt

# 2) 生成 4 张相似样本
python generate_samples.py --image example_images/lion.jpeg \
    --prompt "a lion is sitting in the grass at sunset" --n 4

# 3) 改主体(编辑)生成变体
python generate_samples.py --image example_images/lion.jpeg \
    --prompt "a lion is sitting in the grass at sunset" \
    --variant "a raccoon is sitting in the grass at sunset" --n 3
```

## 参数说明

| 参数 | 说明 | 默认 |
| --- | --- | --- |
| `--image` | 输入图片路径(必填) | - |
| `--prompt` | 对输入图的描述(必填) | - |
| `--variant` | 变体提示词(想改变主体/风格时用) | 同 `--prompt` |
| `--n` | 生成数量 | 4 |
| `--strength` | 去噪强度,越大越偏离原图(0~1) | 0.6 |
| `--steps` | 推理/反演步数(SDXL-Turbo 用 4) | 4 |
| `--model` | 模型 ID | `stabilityai/sdxl-turbo` |
| `--seed` | 起始随机种子(第 i 张用 seed+i) | 7865 |
| `--out` | 输出目录 | `./outputs` |

> 首次运行会从 Hugging Face 下载 SDXL-Turbo 权重(数 GB)。模型权重不随本仓库分发,请确保网络可达。
