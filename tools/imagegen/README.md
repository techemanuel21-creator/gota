# Finishing models for the image painter

The painter (SDXS-512 DreamShaper, one step) is limited by its tiny built-in decoder. The app finishes
each picture with two bigger models that ship **inside the APK** as assets:

| File (`app/src/main/assets/imagegen/`) | What | Size |
|---|---|---|
| `vae_decoder_fp32.pte` | full Stable Diffusion VAE decoder (`vae_large` of `IDKiro/sdxs-512-dreamshaper`), latents → RGB 0..1 | ~198 MB |
| `esrgan_x4_128_fp32.pte` | Real-ESRGAN `realesr-general-x4v3` (BSD-3-Clause), 128 px tile → 512 px | ~5 MB |

The two `.pte` files are **not committed** (see `.gitignore`); regenerate them with `export_models.py`.
Without them the app still works: it falls back to the painter's own decoder and a simple enlarger.

## Regenerate

Python 3.12 with: `torch` (CPU), `diffusers`, `transformers`, `executorch==1.5.1` (same version as the app's
`executorch-android-vulkan` dependency), `pillow`, `numpy`.

1. Download `IDKiro/sdxs-512-dreamshaper` (folders `vae_large`, `tokenizer`, `text_encoder`, `unet`, `vae`).
2. Download `realesr-general-x4v3.pth` from the Real-ESRGAN v0.2.5.0 release.
3. `python export_models.py <sdxs dir> <realesr-general-x4v3.pth> <out dir> 128`
4. Copy the two files into `app/src/main/assets/imagegen/`.

Windows notes: use a short path for the virtual environment (torch has very long file names), install the
Visual C++ 2015–2022 redistributable, and set `FLATC_EXECUTABLE` to
`<venv>\Lib\site-packages\executorch\data\bin\flatc.exe` before exporting.

`verify_export.py` runs the exported files next to the reference PyTorch models and checks the output.
`experiment_steps_and_decoders.py` is the experiment that showed that the painter only works at one step
(2–4 steps turn into mush) and that the full decoder is cleaner than the tiny one.
