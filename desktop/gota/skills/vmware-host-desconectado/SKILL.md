---
name: vmware-host-desconectado
description: Use quando um host ESXi ficar desconectado, "Not Responding" ou o vCenter não o gerenciar.
keywords: vmware, esxi, vcenter, host, desconectado, not responding, hostd, vpxa, psod, vsphere
---
# VMware: host ESXi desconectado ou "Not Responding"

1. As VMs do host continuam rodando? Teste ping do host, porta 443 e o console DCUI/iLO/iDRAC. Se o host está de pé mas desconectado do vCenter, é problema de gerência.
2. No host (SSH ou DCUI): `/etc/init.d/hostd restart` e `/etc/init.d/vpxa restart` (ou `services.sh restart`, com cuidado). Depois, no vCenter: botão direito no host > **Connection > Connect**.
3. Verifique: horário/NTP (diferença quebra autenticação), DNS direto e reverso, disco do ESXi cheio (`df -h`, `vdf -h`), certificado, firewall entre vCenter e host (443/902).
4. Logs: `/var/log/hostd.log`, `/var/log/vpxa.log`, `/var/log/vmkernel.log`; no vCenter `/var/log/vmware/vpxd/vpxd.log`.
5. Tela roxa (PSOD): anote código e pilha, colete o core dump, verifique firmware/driver na HCL e memória do servidor, abra chamado. Reinicie o host e confirme que o HA religou as VMs.
6. Se o problema se repetir, olhe latência de storage (APD), saturação de rede de gerência e memória do host.
