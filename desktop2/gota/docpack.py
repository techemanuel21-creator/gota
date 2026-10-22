"""Downloads documentation for the IT subjects Gota should master and keeps it in the user's knowledge base (%APPDATA%\\Gota\\kb).
The pages are read at the user's request and stay on his computer; they are not part of the program, so nothing here is redistributed."""
import time

from . import kb, tools

# (subject, search queries). Official documentation is ranked first by kb.learn.
TOPICS = [
    # Veeam
    ("Veeam Backup & Replication erros e solução", ["Veeam Backup Replication job failed troubleshooting knowledge base", "Veeam KB error job aborted due to server termination"]),
    ("Veeam Backup & Replication user guide", ["helpcenter.veeam.com Veeam Backup & Replication User Guide"]),
    ("Veeam tape backup", ["Veeam Backup Replication tape infrastructure user guide", "Veeam File to Tape job troubleshooting"]),
    ("Veeam PowerShell reference", ["Veeam Backup Replication PowerShell reference Get-VBRJob"]),
    ("Veeam Used Ports", ["Veeam Backup Replication used ports"]),
    ("Veeam hardened repository immutability", ["Veeam Linux hardened repository immutability"]),
    ("Veeam Backup for Nutanix AHV", ["Veeam Backup for Nutanix AHV user guide"]),
    ("Veeam VSS application-aware processing troubleshooting", ["Veeam VSS application-aware processing failed troubleshooting"]),
    # VMware
    ("VMware vSphere ESXi troubleshooting", ["VMware ESXi host not responding troubleshooting knowledge base", "vSphere troubleshooting guide"]),
    ("VMware vCenter Server", ["VMware vCenter Server appliance administration documentation"]),
    ("VMware vSphere HA DRS vMotion", ["vSphere availability HA DRS vMotion documentation"]),
    ("VMware vSAN", ["VMware vSAN troubleshooting documentation"]),
    ("VMware PowerCLI", ["VMware PowerCLI cmdlet reference examples"]),
    ("esxcli comandos", ["esxcli command reference ESXi"]),
    ("VMware snapshots consolidate", ["VMware snapshots consolidation troubleshooting"]),
    # Hyper-V / Windows
    ("Hyper-V", ["Microsoft Hyper-V on Windows Server documentation"]),
    ("Windows Server Failover Clustering", ["Microsoft Failover Clustering Windows Server documentation"]),
    ("Storage Spaces Direct", ["Microsoft Storage Spaces Direct overview"]),
    ("Active Directory Domain Services", ["Microsoft Active Directory Domain Services troubleshooting replication"]),
    ("Group Policy", ["Microsoft Group Policy troubleshooting gpresult"]),
    ("Windows Server DNS DHCP", ["Windows Server DNS Server DHCP Server documentation"]),
    ("PowerShell", ["Microsoft PowerShell documentation about_ language", "PowerShell Get-WinEvent examples"]),
    ("Windows eventos e desempenho", ["Windows performance troubleshooting perfmon counters documentation"]),
    ("BitLocker e boot do Windows", ["Windows recovery environment bootrec bcdboot documentation"]),
    ("Microsoft 365 Entra ID segurança", ["Microsoft Entra ID conditional access MFA documentation"]),
    # Nutanix
    ("Nutanix AHV", ["Nutanix AHV administration guide"]),
    ("Nutanix Prism e NCC health checks", ["Nutanix NCC health checks knowledge base", "Nutanix Prism Element guide"]),
    ("Nutanix acli ncli comandos", ["Nutanix acli ncli command reference"]),
    ("Nutanix LCM upgrade", ["Nutanix Life Cycle Manager LCM upgrade guide"]),
    # Linux
    ("Linux systemd", ["systemd documentation systemctl journalctl"]),
    ("Linux LVM", ["LVM administration guide Red Hat lvextend"]),
    ("Linux networking", ["Linux ip command nmcli netplan documentation"]),
    ("Linux SELinux", ["SELinux user guide Red Hat troubleshooting"]),
    ("Linux iptables nftables firewalld", ["nftables firewalld documentation"]),
    ("Linux KVM libvirt", ["KVM libvirt virsh documentation"]),
    ("Proxmox VE", ["Proxmox VE administration guide"]),
    ("Linux mdadm RAID", ["mdadm RAID administration guide"]),
    ("Linux SSH", ["OpenSSH sshd_config documentation"]),
    # Redes e segurança
    ("TCP/IP e redes", ["TCP/IP networking fundamentals troubleshooting guide"]),
    ("DNS", ["DNS troubleshooting dig nslookup guide"]),
    ("VLAN STP LACP", ["VLAN trunk spanning tree LACP configuration guide"]),
    ("OSPF BGP", ["OSPF BGP configuration guide"]),
    ("VPN IPsec WireGuard", ["IPsec VPN troubleshooting WireGuard documentation"]),
    ("Wireshark tcpdump", ["Wireshark display filters tcpdump examples"]),
    ("MITRE ATT&CK", ["MITRE ATT&CK enterprise tactics techniques"]),
    ("NIST incident response", ["NIST SP 800-61 computer security incident handling guide"]),
    ("CIS Controls", ["CIS Critical Security Controls v8 overview"]),
    ("OWASP Top 10", ["OWASP Top 10 web application security risks"]),
    ("Ransomware resposta e prevenção", ["CISA ransomware guide response checklist"]),
    ("Kerberos e ataques ao Active Directory", ["Active Directory security Kerberoasting defense documentation"]),
    ("TLS e certificados", ["TLS certificates openssl troubleshooting guide"]),
    ("LGPD", ["LGPD lei geral de proteção de dados resumo incidente de segurança ANPD"]),
    # Armazenamento
    ("RAID níveis", ["RAID levels explained RAID 5 RAID 6 RAID 10"]),
    ("iSCSI e Fibre Channel", ["iSCSI multipath Fibre Channel zoning guide"]),
    ("LTO tape", ["LTO Ultrium tape generations capacity specifications"]),
    ("ZFS", ["OpenZFS documentation zpool"]),
    # Desenvolvimento
    ("Python", ["Python 3 official documentation tutorial standard library"]),
    ("JavaScript MDN", ["MDN JavaScript guide reference"]),
    ("TypeScript", ["TypeScript handbook documentation"]),
    ("Node.js", ["Node.js documentation API"]),
    ("Java", ["Java SE documentation tutorial"]),
    ("C#/.NET", ["Microsoft C# documentation .NET fundamentals"]),
    ("Go", ["Go programming language documentation effective go"]),
    ("Rust", ["The Rust Programming Language book"]),
    ("C e C++", ["C++ reference cppreference documentation"]),
    ("Kotlin", ["Kotlin documentation language reference"]),
    ("PHP", ["PHP manual language reference"]),
    ("Bash", ["GNU Bash reference manual"]),
    ("SQL", ["SQL tutorial PostgreSQL documentation queries"]),
    ("Git", ["Git documentation reference pro git book"]),
    ("Docker", ["Docker documentation Dockerfile reference compose"]),
    ("Kubernetes", ["Kubernetes documentation concepts troubleshooting"]),
    ("Terraform", ["Terraform documentation language"]),
    ("Ansible", ["Ansible documentation playbooks"]),
    ("REST API HTTP", ["MDN HTTP status codes methods headers"]),
    ("Regex", ["regular expressions reference MDN guide"]),
    ("Nginx", ["nginx documentation proxy_pass configuration"]),
    ("PostgreSQL", ["PostgreSQL documentation administration"]),
    ("SQL Server", ["Microsoft SQL Server documentation troubleshooting performance"]),
    # Nuvem e monitoramento
    ("AWS fundamentos", ["AWS documentation EC2 S3 VPC IAM getting started"]),
    ("Azure fundamentos", ["Microsoft Azure documentation virtual machines networking backup"]),
    ("Zabbix", ["Zabbix documentation"]),
    ("Prometheus Grafana", ["Prometheus documentation Grafana getting started"]),
    ("ITIL", ["ITIL 4 incident problem change management overview"]),
]


def have(subject):
    """True when the knowledge base already holds notes learned for this subject."""
    slug = kb._slug(subject)
    return any(f.name.startswith(slug[:30]) for f in kb.KB_DIR.glob("*.md"))


def run(on_status=lambda s: None, should_stop=lambda: False, pages=3, only=None):
    """Downloads every subject not yet in the knowledge base. Returns (subjects done, notes saved). Safe to run again: it resumes."""
    if not tools.is_online():
        on_status("Sem internet: não dá para baixar as documentações agora.")
        return 0, 0
    done = notes = 0
    todo = [t for t in TOPICS if (only is None or any(o.lower() in t[0].lower() for o in only))]
    for i, (subject, queries) in enumerate(todo, 1):
        if should_stop():
            break
        if have(subject):
            done += 1
            continue
        on_status(f"[{i}/{len(todo)}] {subject}")
        try:
            saved = kb.learn(subject, queries=queries, max_pages=pages)
        except Exception:
            saved = []
        notes += len(saved)
        done += 1 if saved else 0
        time.sleep(0.5)
    on_status(f"Pronto: {notes} nota(s) nova(s) guardadas.")
    return done, notes
