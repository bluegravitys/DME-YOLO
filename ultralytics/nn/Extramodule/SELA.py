import torch
import torch.nn as nn


class SELA(nn.Module):
    def __init__(self, channels):
        super(SELA, self).__init__()
        self.pool_h = nn.AdaptiveAvgPool2d((None, 1))
        self.pool_w = nn.AdaptiveAvgPool2d((1, None))
        self.conv1x1 = nn.Sequential(
            nn.Conv1d(channels, channels, 1),
            nn.GroupNorm(16, channels),
            nn.Sigmoid()
        )
        self.qkv = nn.Conv2d(channels, channels * 3, kernel_size=1, bias=False)
        self.softmax = nn.Softmax(dim=-1)
        self.scale = channels ** -0.5

    def forward(self, x):
        b, c, h, w = x.size()

        # ELA Attention
        x_h = self.conv1x1(self.pool_h(x).reshape((b, c, h))).reshape((b, c, h, 1))
        x_w = self.conv1x1(self.pool_w(x).reshape((b, c, w))).reshape((b, c, 1, w))
        ela_out = x * x_h * x_w

        # Softmax Attention
        qkv = self.qkv(x).reshape(b, 3 * c, h * w)
        q, k, v = qkv.chunk(3, dim=1)
        q = q.reshape(b, c, h * w).permute(0, 2, 1)  # B, N, C
        k = k.reshape(b, c, h * w)
        v = v.reshape(b, c, h * w).permute(0, 2, 1)  # B, N, C

        attn = torch.bmm(q, k) * self.scale
        attn = self.softmax(attn)
        softmax_out = torch.bmm(attn, v).permute(0, 2, 1).reshape(b, c, h, w)

        # Fusion of ELA and Softmax Attention
        out = ela_out + softmax_out

        return out


def autopad(k, p=None, d=1):  # kernel, padding, dilation
    """Pad to 'same' shape outputs."""
    if d > 1:
        k = d * (k - 1) + 1 if isinstance(k, int) else [d * (x - 1) + 1 for x in k]  # actual kernel-size
    if p is None:
        p = k // 2 if isinstance(k, int) else [x // 2 for x in k]  # auto-pad
    return p


class Conv(nn.Module):
    """Standard convolution with args(ch_in, ch_out, kernel, stride, padding, groups, dilation, activation)."""
    default_act = nn.SiLU()  # default activation

    def __init__(self, c1, c2, k=1, s=1, p=None, g=1, d=1, act=True):
        """Initialize Conv layer with given arguments including activation."""
        super().__init__()
        self.conv = nn.Conv2d(c1, c2, k, s, autopad(k, p, d), groups=g, dilation=d, bias=False)
        self.bn = nn.BatchNorm2d(c2)
        self.act = self.default_act if act is True else act if isinstance(act, nn.Module) else nn.Identity()

    def forward(self, x):
        """Apply convolution, batch normalization and activation to input tensor."""
        return self.act(self.bn(self.conv(x)))

    def forward_fuse(self, x):
        """Perform transposed convolution of 2D data."""
        return self.act(self.conv(x))


class Bottleneck(nn.Module):
    """Standard bottleneck."""

    def __init__(self, c1, c2, shortcut=True, g=1, k=(3, 3), e=0.5):
        """Initializes a bottleneck module with given input/output channels, shortcut option, group, kernels, and
        expansion.
        """
        super().__init__()
        c_ = int(c2 * e)  # hidden channels
        self.cv1 = Conv(c1, c_, k[0], 1)
        self.cv2 = Conv(c_, c2, k[1], 1, g=g)
        self.add = shortcut and c1 == c2

    def forward(self, x):
        """'forward()' applies the YOLO FPN to input data."""
        return x + self.cv2(self.cv1(x)) if self.add else self.cv2(self.cv1(x))


class C2f_SELA(nn.Module):
    """CSP Bottleneck with 2 convolutions followed by SELA attention."""

    def __init__(self, c1, c2, n=1, shortcut=False, g=1, e=0.5):
        """Initialize CSP bottleneck layer with two convolutions with SELA attention."""
        super().__init__()
        self.c = int(c2 * e)  # hidden channels
        self.cv1 = Conv(c1, 2 * self.c, 1, 1)
        self.cv2 = Conv((2 + n) * self.c, c2, 1)  # optional act=FReLU(c2)
        self.m = nn.ModuleList(Bottleneck(self.c, self.c, shortcut, g, k=((3, 3), (3, 3)), e=1.0) for _ in range(n))
        self.sela = SELA(c2)

    def forward(self, x):
        """Forward pass through C2f layer followed by SELA attention."""
        y = list(self.cv1(x).chunk(2, 1))
        y.extend(m(y[-1]) for m in self.m)
        out = self.cv2(torch.cat(y, 1))
        return self.sela(out)

    def forward_split(self, x):
        """Forward pass using split() instead of chunk() followed by SELA attention."""
        y = list(self.cv1(x).split((self.c, self.c), 1))
        y.extend(m(y[-1]) for m in self.m)
        out = self.cv2(torch.cat(y, 1))
        return self.sela(out)


if __name__ == '__main__':
    x = torch.randn(1, 64, 640, 640)  # Example input
    sela = SELA(64)
    output = sela(x)
    print(output.shape)