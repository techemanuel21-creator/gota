"""Converts the cat's Android vector frames + animation-lists into PNG frames and animations.json."""
import json, re, sys
from pathlib import Path
from PIL import Image, ImageDraw

res = Path(sys.argv[1]); out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
SCALE = 8
def render(xml: str, name):
    n = int(re.search(r'viewportWidth="(\d+)"', xml).group(1))
    img = Image.new("RGBA", (n * SCALE, n * SCALE), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    for color, data in re.findall(r'fillColor="#([0-9A-Fa-f]{8})"\s+android:pathData="([^"]+)"', xml):
        a, r, g, b = (int(color[i:i+2], 16) for i in (0, 2, 4, 6))
        for x, y, w in re.findall(r'M(\d+),(\d+)h(\d+)v1', data):
            x, y, w = int(x), int(y), int(w)
            d.rectangle([x*SCALE, y*SCALE, (x+w)*SCALE-1, (y+1)*SCALE-1], fill=(r, g, b, a))
    img.save(out / f"{name}.png")
frames = set(); anims = {}
for f in sorted(res.glob("anim_*.xml")):
    items = re.findall(r'drawable="@drawable/([^"]+)"\s+android:duration="(\d+)"', f.read_text(encoding="utf-8"))
    anims[f.stem] = [[n, int(ms)] for n, ms in items]; frames |= {n for n, _ in items}
for n in frames: render((res / f"{n}.xml").read_text(encoding="utf-8"), n)
render((res / "cat_idle.xml").read_text(encoding="utf-8"), "logo")
(out / "animations.json").write_text(json.dumps(anims, indent=1), encoding="utf-8")
print(len(frames), "frames,", len(anims), "animations:", ", ".join(anims))
