"""Export the full SD VAE decoder and Real-ESRGAN to ExecuTorch (.pte, XNNPACK).
usage: export_models.py MODEL_DIR ESRGAN_PTH OUT_DIR [tile]"""
import sys, os, time
import torch, torch.nn as nn, torch.nn.functional as F
from diffusers import AutoencoderKL
from torch.export import export
from executorch.exir import to_edge_transform_and_lower
from executorch.backends.xnnpack.partition.xnnpack_partitioner import XnnpackPartitioner

root, esr_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
tile = int(sys.argv[4]) if len(sys.argv) > 4 else 128
os.makedirs(out, exist_ok=True)
torch.set_grad_enabled(False)


def save(module, example, name):
    t0 = time.time()
    ep = export(module.eval(), (example,))
    prog = to_edge_transform_and_lower(ep, partitioner=[XnnpackPartitioner()]).to_executorch()
    path = os.path.join(out, name)
    with open(path, "wb") as f:
        f.write(prog.buffer)
    print(f"{name}: {os.path.getsize(path) / 1e6:.1f} MB, exported in {time.time() - t0:.0f}s", flush=True)


class VaeDecoder(nn.Module):
    """latents (as the UNet makes them) -> RGB in 0..1, like the TAESD export the app uses today."""

    def __init__(self, vae):
        super().__init__()
        self.vae = vae

    def forward(self, z):
        img = self.vae.decode(z / 0.18215).sample
        return ((img + 1) / 2).clamp(0, 1)


class SRVGGNetCompact(nn.Module):
    def __init__(self, num_in_ch=3, num_out_ch=3, num_feat=64, num_conv=32, upscale=4):
        super().__init__()
        self.upscale = upscale
        self.body = nn.ModuleList([nn.Conv2d(num_in_ch, num_feat, 3, 1, 1), nn.PReLU(num_parameters=num_feat)])
        for _ in range(num_conv):
            self.body.append(nn.Conv2d(num_feat, num_feat, 3, 1, 1))
            self.body.append(nn.PReLU(num_parameters=num_feat))
        self.body.append(nn.Conv2d(num_feat, num_out_ch * upscale * upscale, 3, 1, 1))
        self.upsampler = nn.PixelShuffle(upscale)

    def forward(self, x):
        out = x
        for layer in self.body:
            out = layer(out)
        out = self.upsampler(out)
        return (out + F.interpolate(x, scale_factor=self.upscale, mode="nearest")).clamp(0, 1)


vae = AutoencoderKL.from_pretrained(root, subfolder="vae_large", torch_dtype=torch.float32).eval()
save(VaeDecoder(vae), torch.randn(1, 4, 64, 64), "vae_decoder_fp32.pte")

net = SRVGGNetCompact()
net.load_state_dict(torch.load(esr_path, map_location="cpu", weights_only=True)["params"], strict=True)
save(net, torch.rand(1, 3, tile, tile), f"esrgan_x4_{tile}_fp32.pte")
print("EXPORT DONE")
