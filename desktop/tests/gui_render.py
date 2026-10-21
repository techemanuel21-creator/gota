"""Renders a user message and a rich assistant answer (markdown, a Cisco code block, a PowerShell block) in the real window and saves a screenshot. Needs the model file."""
import ctypes
ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
import os, sys, tempfile, traceback
home = tempfile.mkdtemp(); os.environ["GOTA_HOME"] = home; sys.path.insert(0, ".")
out = sys.argv[1]; os.makedirs(out, exist_ok=True)
from gota import store
p = store.Profile(); p.set_name("emanuel", "senhor")
s = store.Settings(); s.set("model_path", os.path.join("models", "gemma4_e2b.litertlm")); s.set("tutorial", True); s.set("cloud_asked", True); s.set("use_cloud", False)
from gota.app import App
from PIL import ImageGrab
app = App()
errors = []
app.report_callback_exception = lambda *a: errors.append("".join(traceback.format_exception(*a)))
state = {"n": 0}
ANSWER = """Pois não, senhor. O script redefine somente as portas pedidas e **não toca na porta 38**.

```cisco
configure terminal
!
vlan 900
 name LINKS
interface range GigabitEthernet1/0/13-27
 description PC/Ramal
 switchport mode access
 switchport access vlan 1
 switchport voice vlan 13
interface GigabitEthernet1/0/41
 description Link02
 switchport access vlan 900
end
write memory
```

## Verificação
- `show vlan brief`
- `show interfaces trunk`

```powershell
Get-NetAdapter | Where-Object Status -eq 'Up' # só as ativas
```"""


def step():
    state["n"] += 1
    app.update()
    if app.gemma is None or not hasattr(app, "entry") or state["n"] < 3:
        return app.after(1000, step)
    if "d" not in state:
        app.attributes("-topmost", True); app.lift(); app.geometry("1097x687+40+10")
        for w in app.msgs.winfo_children():
            w.destroy()
        app.add_message("user", "configurar um switch cisco com as portas e vlans abaixo\n41; Link02\n39 e 40; Lan dos FWs")
        app.add_message("gota", ANSWER)
        state["d"] = state["n"]
        return app.after(1500, step)
    if state["n"] > state["d"] + 2:
        ImageGrab.grab().save(os.path.join(out, "render.png"))
        print("ERROS:", errors or "nenhum", flush=True)
        os._exit(0)
    app.after(1000, step)


app.after(500, step)
app.mainloop()
