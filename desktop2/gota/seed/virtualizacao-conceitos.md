# Virtualização e nuvem: conceitos, dimensionamento e comparações
Fonte: conhecimento base do Gota

## Conceitos
- **Hypervisor tipo 1** (bare metal: ESXi, Hyper-V, AHV, KVM, Xen) e **tipo 2** (sobre SO: VirtualBox, VMware Workstation). **VM** (SO completo) x **contêiner** (processo isolado compartilhando o kernel).
- Recursos: vCPU (mapeia para thread de CPU; mais vCPU nem sempre é mais rápido), RAM (overcommit possível, mas gera ballooning/swap), disco (thin x thick), rede (vSwitch, VLAN, SR-IOV), GPU (passthrough/vGPU), TPM virtual.
- **Overcommit de CPU** típico 3:1 a 5:1 para cargas gerais; menor para banco e VDI crítico. Memória sem overcommit para cargas críticas.
- **NUMA**: VM maior que um nó NUMA sofre latência; dimensione vCPU/RAM cabendo em um nó quando possível.
- **Snapshots/checkpoints**: curta duração; não substituem backup.
- **Templates/clones**, **Cloud-init/sysprep**, **imagem dourada**, **IaC** (Terraform, Ansible, PowerCLI) para repetibilidade.
- **P2V/V2V** (conversão): VMware Converter, Veeam Instant Recovery para outro hypervisor, `qemu-img convert -f vmdk -O qcow2`, `Convert-VHD`, Nutanix Move, Hyper-V Migration; instale drivers (virtio/vmtools/integration services) e ajuste rede/IP após migração.

## Comparação prática
| Item | VMware vSphere | Hyper-V | Nutanix AHV | Proxmox/KVM |
|---|---|---|---|---|
| Gestão | vCenter | SCVMM / WAC / Failover Cluster Manager | Prism | Web UI / CLI |
| Armazenamento | VMFS, NFS, vSAN | CSV, SMB3, S2D | DSF distribuído | LVM, ZFS, Ceph, NFS |
| HA | vSphere HA | Failover Cluster | HA integrado | HA manager (corosync) |
| Formato de disco | VMDK | VHDX | raw/qcow2 (vDisk) | qcow2/raw/zvol |
| CLI | esxcli, PowerCLI | PowerShell | acli/ncli | qm, pvesh, virsh |

## Desempenho: onde olhar
CPU ready (VMware) / CPU wait time (Hyper-V "Virtual Processor"/ready), RAM (ballooning, swap, compression), disco (latência, fila), rede (drops, retransmissões, NIC offloads). Primeiro descubra se o gargalo é no **guest**, no **host** ou no **storage/rede**.

## VDI e aplicações
Horizon, Citrix, Azure Virtual Desktop, RDS: perfis (FSLogix), GPU, protocolo (Blast, HDX, PCoIP, RDP), IOPS no logon (boot storm), imagem gold atualizada.

## Nuvem (básico)
- **IaaS/PaaS/SaaS**, modelo de responsabilidade compartilhada. **AWS** (EC2, S3, EBS, VPC, IAM, RDS, CloudWatch, Route 53), **Azure** (VMs, Blob, VNet, Entra ID, Azure Backup, Site Recovery), **GCP** (Compute Engine, GCS, VPC, IAM).
- Segurança em nuvem: IAM com menor privilégio, MFA, security groups mínimos, S3/Blob nunca público sem necessidade, KMS, logs (CloudTrail, Activity Log), custo (tags, budgets), backup nativo + cópia independente.
- Híbrido: VPN/ExpressRoute/Direct Connect, AD híbrido (Entra Connect), Veeam para cópia em objeto (S3/Azure Blob com imutabilidade).

## IaC e automação
Terraform (`init`, `plan`, `apply`, state remoto), Ansible (playbooks idempotentes, inventário, vault), PowerShell DSC, scripts de verificação, GitOps. Versione tudo, revise mudanças, teste em ambiente isolado.

## Monitoramento e ITIL
- Monitorar disponibilidade, capacidade, desempenho, eventos, backups. Ferramentas: Zabbix, Prometheus + Grafana, Nagios/Icinga, PRTG, LibreNMS, Veeam ONE, vRealize/Aria.
- **Golden signals**: latência, tráfego, erros, saturação. Alertas acionáveis, sem ruído; SLO/SLA.
- **ITIL**: incidente (restaurar serviço), problema (causa raiz), mudança (aprovar, testar, plano de rollback), CMDB, base de conhecimento. Faça **post-mortem sem culpa** com causa raiz, linha do tempo e ações.
