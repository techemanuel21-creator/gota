# Microsoft Hyper-V e Failover Cluster
Fonte: conhecimento base do Gota

## Conceitos
- **Hyper-V** (role no Windows Server): VMs **Geração 1** (BIOS) e **Geração 2** (UEFI, Secure Boot, boot SCSI). Discos **VHD/VHDX** (dinâmico, fixo, diferencial). **Checkpoints** (padrão = produção usa VSS; padrão = standard guarda memória), **memória dinâmica**, **Integration Services**, **vSwitch** externo/interno/privado, **SR-IOV**, **VLAN**, **Live Migration** (CredSSP/Kerberos), **Storage Migration**, **Hyper-V Replica** (assíncrona, RPO 30s/5/15 min).
- **Failover Cluster** (WSFC): nós, **quorum** (witness de disco, compartilhamento ou nuvem), **CSV** (Cluster Shared Volume em `C:\ClusterStorage`), redes de cluster, rede de Live Migration, **Cluster-Aware Updating**. Storage Spaces Direct (**S2D**) forma HCI com discos locais, exige rede RDMA/10-25 GbE e hardware certificado.

## PowerShell essencial
```powershell
Get-VM | Select Name,State,CPUUsage,MemoryAssigned,Uptime
Get-VM | Get-VMSnapshot
Get-VMHost | fl *Migration*
Start-VM NOME ; Stop-VM NOME -TurnOff   # -TurnOff é desligamento forçado
Get-VMNetworkAdapter -VMName NOME
Get-VHD -Path X.vhdx                    # tamanho, fragmentação
Optimize-VHD -Path X.vhdx -Mode Full    # compactar (VM desligada)
Get-Cluster ; Get-ClusterNode ; Get-ClusterGroup ; Get-ClusterResource
Get-ClusterSharedVolume ; Get-ClusterSharedVolumeState
Get-ClusterLog -TimeSpan 30 -Destination C:\Temp     # log de cluster dos últimos 30 min
Test-Cluster                                          # validação (rode antes de produção)
Move-ClusterVirtualMachineRole -Name VM -Node NO2 -MigrationType Live
```
Logs: Visualizador de Eventos > Applications and Services > Microsoft > Windows > **Hyper-V-VMMS**, **Hyper-V-Worker**, **FailoverClustering**, **Hyper-V-Compute**.

## Problemas frequentes
- **VM não inicia**: pouca memória no host, arquivo de disco em uso/bloqueado ("The process cannot access the file") por backup ou antivírus, permissão no VHDX (SID da VM), caminho inexistente, checkpoint corrompido, CPU incompatível ao mover, Secure Boot com SO sem suporte (desative para Linux sem modelo UEFI CA correto).
- **Backup falha** com VSS: Integration Services (Backup/VSS) desatualizado, writer em falha no guest, espaço no host/CSV, checkpoints antigos (merge `.avhdx` pendente), CSV em modo redirecionado.
- **Live Migration falha**: autenticação (Kerberos constrained delegation), rede de migração, processor compatibility, portas SMB 445/6600, nomes diferentes de vSwitch.
- **Cluster: nó "Down/Isolated/Quarantined"**: rede de cluster, heartbeat, tempo, NIC teaming, falhas repetidas põem o nó em quarentena (`Start-ClusterNode -ClearQuarantine`). Perda de quorum derruba tudo: manter número ímpar de votos/witness.
- **CSV "Paused/redirected"**: problema de acesso direto ao storage (iSCSI/FC/driver) ou backup em modo de software; veja `Get-ClusterSharedVolumeState`.
- **Disco VHDX grande e cheio**: dinâmico cresce, não encolhe sozinho; compactar após limpar e fazer `Optimize-VHD`.
- **Rede lenta**: VMQ com NIC Broadcom/Intel antigas (desative VMQ), offloads (LSO/RSC), teaming misto, MTU divergente.
- **Time sync**: Integration Service de tempo conflita com NTP do domínio no DC virtual; deixe DC com PDC emulator sincronizando externo e desative o serviço de tempo do Hyper-V só nele.

## Boas práticas
Host dedicado ao role (sem outros serviços), antivírus com exclusões (`*.vhd, *.vhdx, *.avhd*, *.vmcx, *.vmrs`, pastas de VM, processo `vmms.exe`, `vmwp.exe`), 1 NIC de gerência + NICs de VM + migração/storage separados, checkpoints só temporários, patch por nó com Cluster-Aware Updating, backup de cada VM e do host, monitorar espaço do CSV.
