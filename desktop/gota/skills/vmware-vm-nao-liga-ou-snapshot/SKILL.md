---
name: vmware-vm-nao-liga-ou-snapshot
description: Use quando uma VM VMware não ligar, estiver travada, com snapshot problemático ou disco precisando consolidar.
keywords: vmware, vm, não liga, snapshot, consolidar, datastore cheio, lock, vmdk, delta
---
# VMware: VM não liga ou problemas de snapshot

1. Leia o erro no vSphere (Tasks/Events) e `vmware.log` na pasta da VM.
2. Causas comuns:
   - **Datastore cheio**: libere espaço (snapshots, ISOs, VMs antigas), mova VMs com Storage vMotion ou amplie o LUN e o VMFS.
   - **Recursos insuficientes**: reservas de CPU/memória ou admission control do HA; reduza reservas.
   - **Arquivo bloqueado (.lck)**: outro host ainda detém o disco; confirme que a VM não roda em outro host e só então trate o lock (`vmkfstools -D`, reinicie o host que segura).
   - **Snapshot**: "consolidation needed" = VM > Snapshots > **Consolidate**. Cadeia quebrada ("parent virtual disk has been modified"): não apague arquivos à mão; faça backup e peça ajuda antes de editar descritores.
3. Snapshots são para horas, não dias: delta grande degrada desempenho e demora para consolidar. Backup (Veeam) deve remover seu snapshot ao final; se sobrou, consolide.
4. Depois: ligue a VM, confira o SO e os serviços, e valide se o backup seguinte ocorre sem erro.
