"""SDXS-512 DreamShaper: what do more steps and a better decoder buy?  usage: experiment.py MODEL_DIR OUT_DIR"""
import sys, time, os
import torch
from PIL import Image, ImageDraw
from diffusers import UNet2DConditionModel, AutoencoderTiny, AutoencoderKL
from transformers import CLIPTextModel, CLIPTokenizer

root, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
torch.set_num_threads(8)
torch.set_grad_enabled(False)

tok = CLIPTokenizer.from_pretrained(root, subfolder="tokenizer")
te = CLIPTextModel.from_pretrained(root, subfolder="text_encoder", torch_dtype=torch.float32).eval()
unet = UNet2DConditionModel.from_pretrained(root, subfolder="unet", torch_dtype=torch.float32).eval()
tiny = AutoencoderTiny.from_pretrained(root, subfolder="vae", torch_dtype=torch.float32).eval()
big = AutoencoderKL.from_pretrained(root, subfolder="vae_large", torch_dtype=torch.float32).eval()

betas = torch.linspace(0.00085 ** 0.5, 0.012 ** 0.5, 1000) ** 2
ac = torch.cumprod(1 - betas, 0)

PHOTO = "RAW photo, sharp focus, highly detailed, natural lighting, realistic textures, 8k uhd"
ART = "clean crisp lines, highly detailed, sharp focus, smooth shading, high quality"
PROMPTS = {
    "butler": f"a gray cat butler wearing a black bow tie and a white shirt, drinking tea from a cup, {PHOTO}",
    "roof": f"a tabby cat sitting on a rooftop at night, city lights, full moon, {PHOTO}",
    "cartoon": f"a cartoon white cat butler serving tea in a cozy room, {ART}",
}
SCHEDULES = {1: [999], 2: [999, 500], 3: [999, 750, 500], 4: [999, 800, 600, 400]}


def embed(prompt):
    ids = tok(prompt, padding="max_length", max_length=77, truncation=True, return_tensors="pt").input_ids
    return te(ids)[0]


def x0_pred(x, t, emb):
    e = unet(x, torch.tensor([t]), encoder_hidden_states=emb).sample
    a = ac[t]
    return (x - (1 - a).sqrt() * e) / a.sqrt()


def decode(lat, which):
    img = tiny.decode(lat).sample if which == "tiny" else big.decode(lat / 0.18215).sample
    img = ((img.clamp(-1, 1) + 1) / 2 * 255).round().byte()[0].permute(1, 2, 0).numpy()
    return Image.fromarray(img)


def sample(emb, steps, seed):
    g = torch.Generator().manual_seed(seed)
    x = torch.randn(1, 4, 64, 64, generator=g)
    ts = SCHEDULES[steps]
    x0 = None
    for i, t in enumerate(ts):
        x0 = x0_pred(x, t, emb)
        if i + 1 < len(ts):
            tn = ts[i + 1]
            # fresh noise at the next (lower) noise level, like a consistency model
            x = ac[tn].sqrt() * x0 + (1 - ac[tn]).sqrt() * torch.randn(1, 4, 64, 64, generator=g)
    return x0


def label(img, text):
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 512, 22], fill=(0, 0, 0))
    d.text((6, 5), text, fill=(255, 255, 255))
    return img


start = time.time()
for name, prompt in PROMPTS.items():
    emb = embed(prompt)
    for seed in (11, 12):
        cols = []
        x1 = sample(emb, 1, seed)
        cols.append(label(decode(x1, "tiny"), "1 step + tiny decoder (today)"))
        cols.append(label(decode(x1, "big"), "1 step + full decoder"))
        for k in (2, 3, 4):
            cols.append(label(decode(sample(emb, k, seed), "big"), f"{k} steps + full decoder"))
        sheet = Image.new("RGB", (512 * len(cols), 512))
        for i, c in enumerate(cols):
            sheet.paste(c, (512 * i, 0))
        sheet.save(os.path.join(out, f"{name}_{seed}.png"))
        print(f"{name} seed {seed} done at {time.time() - start:.0f}s", flush=True)
print("ALL DONE", flush=True)
