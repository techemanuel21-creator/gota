"""Check the exported VAE decoder + Real-ESRGAN tiles against torch.  usage: verify_export.py MODEL_DIR EXPORT_DIR PTE_UNET OUT_DIR"""
import sys, os, time, threading
import numpy as np
import torch, torch.nn.functional as F
import psutil
from PIL import Image
from diffusers import UNet2DConditionModel, AutoencoderKL
from transformers import CLIPTextModel, CLIPTokenizer
from executorch.runtime import Runtime

root, exp, out = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(out, exist_ok=True)
torch.set_grad_enabled(False)
proc = psutil.Process()
peak = [0]


def watch():
    while True:
        peak[0] = max(peak[0], proc.memory_info().rss)
        time.sleep(0.05)


threading.Thread(target=watch, daemon=True).start()
mb = lambda b: f"{b / 1e6:.0f} MB"

tok = CLIPTokenizer.from_pretrained(root, subfolder="tokenizer")
te = CLIPTextModel.from_pretrained(root, subfolder="text_encoder", torch_dtype=torch.float32).eval()
unet = UNet2DConditionModel.from_pretrained(root, subfolder="unet", torch_dtype=torch.float32).eval()
big = AutoencoderKL.from_pretrained(root, subfolder="vae_large", torch_dtype=torch.float32).eval()

PHOTO = "RAW photo, sharp focus, highly detailed, natural lighting, realistic textures, 8k uhd"
ids = tok(f"a gray cat butler wearing a black bow tie and a white shirt, drinking tea from a cup, {PHOTO}",
          padding="max_length", max_length=77, truncation=True, return_tensors="pt").input_ids
emb = te(ids)[0]
x = torch.randn(1, 4, 64, 64, generator=torch.Generator().manual_seed(11))
e = unet(x, torch.tensor([999]), encoder_hidden_states=emb).sample
x0 = 14.648819 * x - 14.614648 * e

rt = Runtime.get()
before = proc.memory_info().rss
vae = rt.load_program(os.path.join(exp, "vae_decoder_fp32.pte")).load_method("forward")
t0 = time.time(); img_pte = vae.execute([x0])[0]; t_vae = time.time() - t0
print(f"VAE decoder: {t_vae:.1f}s on this PC | process memory before {mb(before)}, peak so far {mb(peak[0])}", flush=True)
ref = ((big.decode(x0 / 0.18215).sample + 1) / 2).clamp(0, 1)
print("  max |pte - torch| =", float((img_pte - ref).abs().max()), " mean =", float((img_pte - ref).abs().mean()), flush=True)
arr = img_pte[0].permute(1, 2, 0).numpy()
Image.fromarray((arr * 255 + 0.5).astype(np.uint8)).save(os.path.join(out, "vae_pte.png"))

# ---- Real-ESRGAN in 128 px tiles, 32 px overlap, blended ----
T, O, S = 128, 32, 4
esr = rt.load_program(os.path.join(exp, "esrgan_x4_128_fp32.pte")).load_method("forward")
H = W = 512
stride = T - O
pos = list(range(0, H - T + 1, stride))
if pos[-1] + T < H:
    pos.append(H - T)
print("tile positions:", pos, "->", len(pos) ** 2, "tiles", flush=True)
acc = torch.zeros(1, 3, H * S, W * S)
wsum = torch.zeros(1, 1, H * S, W * S)
ramp = O * S


def window(first, last):
    u = torch.arange(T * S, dtype=torch.float32)
    w = torch.minimum(u, (T * S - 1) - u) / ramp
    w = w.clamp(1e-3, 1.0)
    if first: w[: T * S // 2] = torch.maximum(w[: T * S // 2], torch.ones(T * S // 2) * 0)  # replaced below
    return w


def axis_weights(i, n):
    u = torch.arange(T * S, dtype=torch.float32)
    left = (u / ramp).clamp(1e-3, 1.0) if i > 0 else torch.ones(T * S)
    right = (((T * S - 1) - u) / ramp).clamp(1e-3, 1.0) if i < n - 1 else torch.ones(T * S)
    return torch.minimum(left, right)


t0 = time.time()
img = img_pte
for iy, y in enumerate(pos):
    for ix, xx in enumerate(pos):
        tile = img[:, :, y:y + T, xx:xx + T].contiguous()
        up = esr.execute([tile])[0]
        w = axis_weights(iy, len(pos))[:, None] * axis_weights(ix, len(pos))[None, :]
        acc[:, :, y * S:(y + T) * S, xx * S:(xx + T) * S] += up * w
        wsum[:, :, y * S:(y + T) * S, xx * S:(xx + T) * S] += w
t_esr = time.time() - t0
result = (acc / wsum).clamp(0, 1)
print(f"Real-ESRGAN tiles: {t_esr:.1f}s on this PC | peak process memory {mb(peak[0])}", flush=True)
Image.fromarray((result[0].permute(1, 2, 0).numpy() * 255 + 0.5).astype(np.uint8)).save(os.path.join(out, "final_2048.png"))
print("DONE", flush=True)
