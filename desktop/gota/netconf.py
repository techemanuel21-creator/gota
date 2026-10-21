"""Instant Cisco port/VLAN scripts: when the request is a table of ports ("41; Link02", "28 a 37; Antenas", ...) under headings such as "Trunk:" or
"Vlan acess 1 e voice vlan 13:", the script is built here, in milliseconds and exactly as the rules of the cisco-configurar-portas-e-vlans skill say,
instead of asking a model to write it (10 to 70 seconds). Anything that does not parse cleanly returns None and goes to the model as before."""
import re
from . import tools

PORT_LINE = re.compile(r"^\s*(\d[\d\s,ea-]*?)\s*;\s*(.+?)\s*$", re.I)
CONTEXT = re.compile(r"\b(switch|cisco|vlan|trunk|switchport|portas?)\b", re.I)


def parse_ports(expr):
    """"28 a 37" -> 28..37; "39 e 40" -> [39, 40]; "1, 3, 5" -> [1, 3, 5]. None if it is not a clean list of ports."""
    ports = []
    for part in re.split(r"\s*(?:,|\be\b)\s*", expr.strip(), flags=re.I):
        m = re.fullmatch(r"(\d+)\s*(?:a|-|até|ate)\s*(\d+)", part.strip(), re.I)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            if hi < lo or hi - lo > 96:
                return None
            ports += list(range(lo, hi + 1))
        elif part.strip().isdigit():
            ports.append(int(part))
        else:
            return None
    return ports or None


def ranges(ports):
    """[1,2,3,5] -> [(1,3),(5,5)]"""
    out = []
    for p in sorted(set(ports)):
        if out and p == out[-1][1] + 1:
            out[-1] = (out[-1][0], p)
        else:
            out.append((p, p))
    return out


def _heading(line):
    """(mode, access_vlan, voice_vlan, vlan_is_new) for a heading line, or None when it is not one."""
    low = tools.norm(line)
    if ";" in line or not re.search(r"vlan|trunk", low):
        return None
    if "trunk" in low:
        return ("trunk", None, None, False)
    voice = re.search(r"voice\s*vlan\s*(\d+)", low)
    access = re.search(r"vlan\s*(?:acess|access|acesso)\s*(\d+)", low) or re.search(r"\bvlan\s*(\d+)\b(?!.*voice)", low)
    if access:
        return ("access", int(access.group(1)), int(voice.group(1)) if voice else None, bool(re.search(r"nao existe|ainda nao|nova|criar", low)))
    return None


def parse(text):
    """The request as groups [{ports, label, mode, vlan, voice}] plus the VLANs to create, or None."""
    if not CONTEXT.search(text):
        return None
    groups, new_vlans, voice_vlans, head = [], [], [], None
    for line in text.splitlines():
        if not line.strip():
            continue
        h = _heading(line)
        if h:
            head = h
            if h[3] and h[1] not in new_vlans:
                new_vlans.append(h[1])
            if h[2] and h[2] not in voice_vlans:
                voice_vlans.append(h[2])
            continue
        m = PORT_LINE.match(line)
        if m:
            ports = parse_ports(m.group(1))
            if ports is None or head is None:
                return None
            groups.append({"ports": ports, "label": m.group(2).strip(), "mode": head[0], "vlan": head[1], "voice": head[2]})
    if len(groups) < 2:
        return None
    seen = [p for g in groups for p in g["ports"]]
    if len(seen) != len(set(seen)):   # a port listed twice: ambiguous, let the model/user sort it out
        return None
    return {"groups": groups, "new_vlans": new_vlans, "voice_vlans": voice_vlans}


def script(spec, prefix="GigabitEthernet1/0/"):
    def iface(lo, hi):
        return f"{prefix}{lo}" if lo == hi else f"{prefix}{lo}-{hi}"
    lines = ["configure terminal"]
    for v in spec["new_vlans"] + [v for v in spec["voice_vlans"] if v not in spec["new_vlans"]]:
        lines += [f"vlan {v}", "exit"]
    allports = [p for g in spec["groups"] for p in g["ports"]]
    for lo, hi in ranges(allports):
        lines.append(f"default interface range {iface(lo, hi)}")
    for g in sorted(spec["groups"], key=lambda g: min(g["ports"])):
        rs = ranges(g["ports"])
        single = len(g["ports"]) == 1
        lines.append((f"interface {prefix}{g['ports'][0]}" if single else "interface range " + ", ".join(iface(lo, hi) for lo, hi in rs)))
        lines.append(f" description {g['label']}")
        if g["mode"] == "trunk":
            lines.append(" switchport mode trunk")
        else:
            lines += [" switchport mode access", f" switchport access vlan {g['vlan']}"]
            if g["voice"]:
                lines.append(f" switchport voice vlan {g['voice']}")
        lines.append("exit")
    lines += ["end", "write memory"]
    return "\n".join(lines)


def try_answer(text, sir="senhor"):
    """The full reply (text + code block) or None when the request is not a clean port table."""
    spec = parse(text)
    if spec is None:
        return None
    allports = sorted(p for g in spec["groups"] for p in g["ports"])
    gaps = [p for p in range(allports[0], allports[-1] + 1) if p not in allports]
    notes = ["Usei `GigabitEthernet1/0/N` (em switch de 1 chassi pode ser `GigabitEthernet0/N`; confira com `show ip interface brief`).",
             "Nos trunks não restringi VLANs permitidas nem a nativa, porque o pedido não falou: o padrão permite todas."]
    if gaps:
        notes.insert(0, "Não mexi na(s) porta(s) " + ", ".join(map(str, gaps)) + ", que não estavam na lista.")
    if any(g["mode"] == "trunk" for g in spec["groups"]):
        notes.append("Em Catalyst antigo (3560/3750) coloque `switchport trunk encapsulation dot1q` antes de `switchport mode trunk`.")
    if spec["voice_vlans"]:
        notes.append("`vlan " + ", ".join(map(str, spec["voice_vlans"])) + "` só garante que a VLAN existe; se já existir, nada muda.")
    return (f"Pois não, {sir}. Script pronto: reseta só as portas listadas e configura cada grupo.\n\n```cisco\n" + script(spec) + "\n```\n\n" + "\n".join(f"- {n}" for n in notes))
