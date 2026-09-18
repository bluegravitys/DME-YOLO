"""
generate_samples.py — Generate N "similar" images from ONE input image using
GNRI (Guided Newton-Raphson Inversion) with SDXL-Turbo.

What it does
------------
1. Invert the input image to a noise latent (Newton-Raphson inversion). This is
   the expensive-but-cheap-in-practice step (fraction of a second on a GPU for
   few-step models).
2. Re-generate N variants from that latent. Each variant uses a different random
   noise seed, so you get "the same subject, slightly different" samples. You can
   also pass a --variant prompt to change attributes (e.g. "lion" -> "raccoon").

This is image-to-image **editing / augmentation**, not text-to-image generation:
you MUST supply an input image.

Hardware requirement: an NVIDIA GPU with CUDA (code paths assume CUDA; SDXL-Turbo
on CPU is impractically slow). First run downloads `stabilityai/sdxl-turbo`
(several GB) from Hugging Face into a local cache.

Quick start (run from this `inversion/` folder):
    pip install -r requirements.txt
    python generate_samples.py --image /path/to/input.jpg \
        --prompt "a photo of ..." --n 4

Flags:
    --image     path to the input image (required)
    --prompt    caption describing the input image (required)
    --variant   optional edit prompt; defaults to --prompt (same subject)
    --n         number of images to generate (default 4)
    --strength  denoising strength in (0,1]; higher => more deviation from input
    --steps     inference/inversion steps (SDXL-Turbo uses 4; default 4)
    --model     HF model id (default stabilityai/sdxl-turbo)
    --seed      base random seed (default 7865); samples use seed, seed+1, ...
    --out       output directory (default ./outputs)
"""

import argparse
import os
import sys

import torch
from PIL import Image

# Make sibling `src` package importable regardless of the current working directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from diffusers import AutoPipelineForImage2Image
from diffusers.utils.torch_utils import randn_tensor

from src.config import RunConfig
from src.euler_scheduler import MyEulerAncestralDiscreteScheduler
from src.sdxl_inversion_pipeline import SDXLDDIMPipeline

IMAGE_SIZE = 512          # SDXL-Turbo native resolution used throughout the demo
LATENT_SIZE = IMAGE_SIZE // 8  # 64


def center_crop_resize(im, size=IMAGE_SIZE):
    """Center-crop a square and resize, matching the original main.py preprocessing."""
    im = im.convert("RGB")
    w, h = im.size
    m = min(w, h)
    left, top = (w - m) // 2, (h - m) // 2
    return im.crop((left, top, left + m, top + m)).resize((size, size))


def build_pipelines(model, device, cache_dir):
    pipe_inversion = SDXLDDIMPipeline.from_pretrained(
        model, use_safetensors=True, safety_checker=None, cache_dir=cache_dir
    ).to(device)
    pipe_inference = AutoPipelineForImage2Image.from_pretrained(
        model, use_safetensors=True, safety_checker=None, cache_dir=cache_dir
    ).to(device)

    inv_sched = MyEulerAncestralDiscreteScheduler.from_config(pipe_inversion.scheduler.config)
    inf_sched = MyEulerAncestralDiscreteScheduler.from_config(pipe_inference.scheduler.config)

    pipe_inversion.scheduler = inv_sched
    pipe_inversion.scheduler_inference = inf_sched
    pipe_inference.scheduler = inf_sched
    return pipe_inversion, pipe_inference


class Inverter:
    """Parameterized mirror of the original `ImageEditorDemo` from main.py."""

    def __init__(self, pipe_inversion, pipe_inference, image_path, cfg, seed, device, dtype):
        self.pipe_inversion = pipe_inversion
        self.pipe_inference = pipe_inference
        self.original_image = center_crop_resize(Image.open(image_path))
        self.cfg = cfg
        self.pipe_inversion.cfg = cfg
        self.pipe_inference.cfg = cfg
        self.inv_hp = [2, 0.1, 0.2]
        self.edit_cfg = 1.2
        self.device = device
        self.dtype = dtype
        self.noise = self._make_noise(seed)

    def _make_noise(self, seed):
        g = torch.Generator(device="cpu").manual_seed(seed)
        latents_size = (1, 4, LATENT_SIZE, LATENT_SIZE)
        return [
            randn_tensor(latents_size, dtype=self.dtype, device=self.device, generator=g)
            for _ in range(self.cfg.num_inversion_steps)
        ]

    def _set_noise(self):
        self.pipe_inversion.scheduler.set_noise_list(self.noise)
        self.pipe_inference.scheduler.set_noise_list(self.noise)
        self.pipe_inversion.scheduler_inference.set_noise_list(self.noise)

    def invert(self, prompt):
        """Run Newton-Raphson inversion; returns the image noise latent."""
        self._set_noise()
        self.pipe_inversion.set_progress_bar_config(disable=True)
        res = self.pipe_inversion(
            prompt=prompt,
            num_inversion_steps=self.cfg.num_inversion_steps,
            num_inference_steps=self.cfg.num_inference_steps,
            image=self.original_image,
            guidance_scale=self.cfg.guidance_scale,
            strength=self.cfg.inversion_max_step,
            denoising_start=1.0 - self.cfg.inversion_max_step,
            inv_hp=self.inv_hp,
        )[0][0]
        return res

    def generate(self, latent, prompt, strength):
        """Re-generate an image from the inverted latent (same call shape as original `edit`)."""
        self._set_noise()
        self.pipe_inference.set_progress_bar_config(disable=True)
        image = self.pipe_inference(
            prompt=prompt,
            num_inference_steps=self.cfg.num_inference_steps,
            negative_prompt="",
            image=latent,
            strength=strength,
            denoising_start=1.0 - strength,
            guidance_scale=self.edit_cfg,
        ).images[0]
        return image


def main():
    ap = argparse.ArgumentParser(description="Generate N similar image samples with GNRI inversion.")
    ap.add_argument("--image", required=True, help="input image path")
    ap.add_argument("--prompt", required=True, help="caption describing the input image")
    ap.add_argument("--variant", default=None, help="optional edit prompt (default: same as --prompt)")
    ap.add_argument("--n", type=int, default=4, help="number of images to generate")
    ap.add_argument("--strength", type=float, default=0.6, help="denoising strength (higher => more deviation)")
    ap.add_argument("--steps", type=int, default=4, help="inference/inversion steps (sdxl-turbo uses 4)")
    ap.add_argument("--model", default="stabilityai/sdxl-turbo")
    ap.add_argument("--out", default="./outputs")
    ap.add_argument("--seed", type=int, default=7865)
    args = ap.parse_args()

    if not torch.cuda.is_available():
        print("WARNING: no CUDA GPU detected. SDXL-Turbo on CPU is extremely slow; "
              "an NVIDIA GPU is strongly recommended.", file=sys.stderr)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    dtype = torch.float16 if device.type == "cuda" else torch.float32

    cache_dir = os.environ.get("HF_HOME") or os.path.join(os.path.expanduser("~"), ".cache", "huggingface")
    os.makedirs(cache_dir, exist_ok=True)

    print(f"Loading model '{args.model}' ... (first run downloads several GB)")
    pipe_inversion, pipe_inference = build_pipelines(args.model, device, cache_dir)

    cfg = RunConfig(
        num_inference_steps=args.steps,
        num_inversion_steps=args.steps,
        guidance_scale=0.0,
        inversion_max_step=args.strength,
    )

    inverter = Inverter(pipe_inversion, pipe_inference, args.image, cfg, args.seed, device, dtype)

    print("Inverting input image (Newton-Raphson) ...")
    latent = inverter.invert(args.prompt)

    variant = args.variant or args.prompt
    os.makedirs(args.out, exist_ok=True)
    base = os.path.splitext(os.path.basename(args.image))[0]

    print(f"Generating {args.n} samples (strength={args.strength}, seed={args.seed}..{args.seed + args.n - 1}) ...")
    for i in range(args.n):
        inverter.noise = inverter._make_noise(args.seed + i)
        img = inverter.generate(latent, variant, args.strength)
        out_path = os.path.join(args.out, f"{base}_sample_{i:02d}.png")
        img.save(out_path)
        print(f"  saved {out_path}")

    print("Done.")


if __name__ == "__main__":
    main()
