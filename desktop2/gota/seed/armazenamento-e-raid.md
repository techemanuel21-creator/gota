# Armazenamento: RAID, SAN/NAS, iSCSI, FC, NFS, SMB, desempenho e diagnóstico
Fonte: conhecimento base do Gota

## RAID
- **RAID 0** (stripe: desempenho, sem proteção), **RAID 1** (espelho), **RAID 5** (paridade simples; tolera 1 disco; penalidade de escrita 4 I/Os; risco no rebuild de discos grandes), **RAID 6** (paridade dupla; tolera 2; penalidade 6), **RAID 10** (espelhos em stripe; bom para escrita aleatória e bancos), **RAID 50/60** (grupos de paridade em stripe).
- Capacidade útil: R5 = (N-1) discos; R6 = (N-2); R10 = N/2. **Hot spare** reconstrói automaticamente. RAID **não é backup**.
- Rebuild lento + disco grande + disco do mesmo lote = risco de segunda falha: prefira RAID 6/10 para discos grandes e monitore SMART.

## SAN x NAS, protocolos
- **SAN** entrega blocos (LUNs) por **Fibre Channel** (FC, zoning/WWN) ou **iSCSI** (TCP; use rede dedicada, jumbo frames MTU 9000 ponta a ponta, multipath). **NAS** entrega arquivos por **SMB/CIFS** (Windows) ou **NFS** (Unix/VMware).
- **Multipath (MPIO)**: vários caminhos ao LUN para redundância e balanceamento. **LUN masking/zoning** controlam quem enxerga o quê.
- **Thin provisioning** (aloca sob demanda; monitore o over-commit), **dedup/compressão**, **snapshots** (mesmo storage, não são backup), **replicação** síncrona (RPO 0, latência baixa) ou assíncrona.
- **Objeto (S3)**: buckets, versionamento, **Object Lock** (imutabilidade), classes de armazenamento.

## Desempenho
- Métricas: **IOPS**, **throughput** (MB/s), **latência** (ms), profundidade de fila. Banco OLTP: latência baixa e IOPS aleatório; backup/stream: throughput sequencial.
- Latência saudável típica: SSD < 1-2 ms; discos SAS 10-20 ms. Latência alta + fila cheia = gargalo no storage ou no caminho (rede, HBA, switch).
- Ferramentas: Windows `perfmon` (PhysicalDisk: Avg. Disk sec/Read e /Write, Disk Queue Length), `diskspd`; Linux `iostat -x 1`, `iotop`, `fio`; VMware `esxtop` (DAVG, KAVG, GAVG), Nutanix Prism (IOPS/latência por VM).
- Causas de lentidão: discos saturados, RAID degradado/rebuild, cache com bateria falha, caminhos inativos (multipath), MTU diferente, switch congestionado, antivírus, snapshots longos, alinhamento de partições, fragmentação de arquivos pequenos.

## Diagnóstico de disco
- Linux: `lsblk`, `blkid`, `smartctl -a /dev/sdX`, `dmesg | grep -i -E 'ata|scsi|I/O error'`, `mdadm --detail /dev/md0`, `cat /proc/mdstat`, `pvs/vgs/lvs`, `df -h`, `df -i`.
- Windows: `Get-PhysicalDisk | Select FriendlyName,HealthStatus,OperationalStatus`, `Get-Volume`, `chkdsk /scan`, `Get-StorageReliabilityCounter`, eventos disk/ntfs (ID 7, 11, 51, 153, 55).
- Controladora: logs do iDRAC/iLO/StorCLI/MegaCli (`storcli /c0 show`), estado de bateria/cache, discos "predictive failure".

## Fita e longo prazo
LTO é barato por TB, ótimo para arquivamento e cópia offline. Veja veeam-fita-tape.md. Ciclo de vida: verifique a leitura de mídias antigas, mantenha drive compatível, registre retenção.

## Sistemas de arquivos
ext4 (padrão Linux), **XFS** (grandes volumes, não encolhe), **Btrfs/ZFS** (snapshots, checksum; ZFS: pools, vdevs, scrub, ARC), **NTFS** (permissões ACL, compressão), **ReFS** (resiliência, integrity streams, usado com Hyper-V/Storage Spaces), **VMFS** (VMware), **exFAT/FAT32** (mídias removíveis). Cotas, ACLs, permissões herdadas e propriedade de arquivos explicam muitos erros de "acesso negado".
