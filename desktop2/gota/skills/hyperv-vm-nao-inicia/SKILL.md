---
name: hyperv-vm-nao-inicia
description: Use quando uma VM Hyper-V não iniciar, travar ou o backup/migração falhar.
keywords: hyper-v, vm, não inicia, vhdx, checkpoint, avhdx, live migration, cluster, csv
---
# Hyper-V: VM não inicia ou falha

1. Leia o erro completo e os logs **Hyper-V-VMMS/Admin** e **Hyper-V-Worker** no Visualizador de Eventos.
2. Verifique: memória livre no host, caminho do VHDX existente, **arquivo em uso** (backup, antivírus), permissão do VHDX para a VM (`icacls`), espaço no volume/CSV, checkpoints (`.avhdx`) pendentes de merge.
3. Geração 2 com Linux: desmarque Secure Boot ou use o modelo UEFI para Linux. CPU incompatível ao mover: ative "processor compatibility".
4. Cluster: `Get-ClusterGroup`, `Get-ClusterSharedVolumeState` (CSV "Paused/redirected" indica problema de acesso ao storage), nó em quarentena (`Start-ClusterNode -ClearQuarantine`), quorum/witness.
5. Backup falhando: Integration Services atualizados, VSS writers ok dentro do guest, checkpoints antigos, espaço no host.
6. Após corrigir, inicie (`Start-VM NOME`) e confirme serviços; exclua checkpoints antigos com a VM ligada (merge em segundo plano).
