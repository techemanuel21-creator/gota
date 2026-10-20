# VMware vSphere: ESXi, vCenter, HA/DRS, vMotion, snapshots, datastores, vSAN
Fonte: conhecimento base do Gota (confirme na documentação da Broadcom/VMware para a versão em uso)

## Arquitetura
- **ESXi** (hypervisor, bare metal), **vCenter Server** (gestão central, appliance VCSA; serviços: vpxd, vsphere-ui, vmware-vpostgres), **cluster** (conjunto de hosts), **datastore** (VMFS em LUN, NFS ou vSAN), **vSwitch/vDS** (rede virtual; portgroups, VLAN), **vmkernel** (gerência, vMotion, vSAN, iSCSI, FT).
- Recursos de cluster: **HA** (reinicia VMs se o host cair; heartbeat por rede e datastore, admission control), **DRS** (balanceamento e vMotion automático), **vMotion** (migra VM ligada), **Storage vMotion**, **FT**, **EVC** (compatibilidade de CPU), **Resource Pools**, **vSphere Replication**.
- Licenciamento e versões mudam; confirme requisitos de compatibilidade em compatibilityguide.broadcom.com (HCL) antes de atualizar.

## Comandos úteis no ESXi (SSH ou console)
```sh
esxcli system version get                      # versão/build
esxcli hardware memory get ; esxcli hardware cpu global get
vim-cmd vmsvc/getallvms                        # lista VMs e IDs
vim-cmd vmsvc/power.getstate <id> ; vim-cmd vmsvc/power.on <id>
vim-cmd vmsvc/snapshot.get <id>                # snapshots da VM
esxcli storage core device list                # discos/LUNs
esxcli storage nmp device list                 # multipath e política (VMW_PSP_RR etc.)
esxcli storage vmfs extent list ; df -h        # datastores
esxcli network nic list ; esxcli network ip interface list
esxcli network ip connection list              # conexões
vmkping -I vmk0 <ip>                           # ping pela interface vmkernel (use -d -s 8972 para testar MTU 9000)
esxtop                                         # c=cpu, m=mem, d=disco, n=rede, u=dispositivos
services.sh restart                            # reinicia serviços de gerência (cuidado)
/etc/init.d/hostd restart ; /etc/init.d/vpxa restart   # hostd e agente do vCenter
```
Logs no ESXi: `/var/log/vmkernel.log`, `/var/log/hostd.log`, `/var/log/vpxa.log`, `/var/log/vobd.log`, `/var/log/vmkwarning.log`, `/var/log/fdm.log` (HA). Por VM: `vmware.log` na pasta da VM. No VCSA: `/var/log/vmware/vpxd/vpxd.log`, `/var/log/vmware/vmware-vpostgres/`, comando `service-control --status --all`, `df -h` (partições cheias derrubam o vCenter: cheque `/storage/log`, `/storage/seat`, `/storage/db`).

## Problemas frequentes
- **Host "Not Responding"/desconectado**: ping/porta 443/902, serviço hostd/vpxa travado (reiniciar), DNS/horário (NTP), disco root cheio, certificado. Reconecte no vCenter depois de corrigir (Connect).
- **PSOD (tela roxa)**: anote o erro e a pilha; geralmente hardware (memória, CPU), driver/firmware fora da HCL, ou bug da build. Colete o core dump e abra chamado; atualize firmware/driver.
- **VM não liga**: "Insufficient resources" (reserva/admission control), arquivo `.lck` preso, disco bloqueado por outro host, datastore cheio, snapshot corrompido, licença. Veja `vmware.log` e Tasks/Events.
- **Snapshots**: não são backup; delta cresce e degrada desempenho; consolide; nunca apague arquivos `-delta.vmdk` à mão; cadeia quebrada ("The parent virtual disk has been modified") exige corrigir o descritor com cuidado e backup antes.
- **Datastore cheio**: VMs travam (pergunta de "I/O error"), libere espaço (snapshots, ISO, swap, thin), aumente o LUN e estenda o VMFS, mova VMs (Storage vMotion).
- **APD / PDL**: All Paths Down (caminhos perdidos, pode voltar) e Permanent Device Loss (dispositivo removido). Verifique SAN, zoning, cabos, multipath, HBA; configure respostas de HA (VM Component Protection).
- **Latência de disco**: `esxtop` tela d: DAVG (dispositivo), KAVG (kernel/fila), GAVG (guest = DAVG+KAVG). GAVG > 20-30 ms é preocupante.
- **CPU ready alto** (>5-10% por vCPU): excesso de vCPUs, host sobrecarregado; reduza vCPUs, balanceie, cuidado com VMs de muitos vCPUs.
- **Memória**: ballooning, swapping e compressão indicam falta de RAM no host; reserve, reduza ou adicione RAM.
- **vMotion falha**: rede vMotion/MTU, CPUs incompatíveis (EVC), datastore não compartilhado, dispositivos conectados (CD/USB), nomes de portgroup diferentes.
- **HA "agent unreachable/failed"**: rede de gerência, DNS, reconfigurar HA no host, `fdm.log`.
- **Certificado/tempo**: NTP errado quebra autenticação; use `chronyd`/NTP no ESXi e vCenter.
- **vCenter lento/não sobe**: disco cheio, banco, serviços; `service-control --start --all`; verifique snapshots do próprio VCSA e backup/restauração nativos (VAMI porta 5480).

## vSAN (resumo)
Discos locais agregados em datastore distribuído. **Disk groups** (cache + capacidade), **políticas de armazenamento** (FTT, RAID-1/5/6), **resync** após falha, **componentes absent/degraded** (diferenciar ausente de degradado), `esxcli vsan` e Skyline Health. Rede vSAN dedicada e estável; atenção a manutenção host a host (modo de manutenção com "ensure accessibility").

## Boas práticas
Patching por LCM/Update Manager em ordem (vCenter primeiro, depois hosts); modo de manutenção; NTP; backup do VCSA; separar redes (gerência, vMotion, storage, VM); desativar SSH quando não usado; hardening (lockdown mode, ACL, MFA via IdP); snapshots por poucas horas; monitorar com vRealize/Aria, Grafana ou Veeam ONE.

## PowerCLI
```powershell
Connect-VIServer vcenter.local
Get-VM | Select Name,PowerState,NumCpu,MemoryGB,VMHost
Get-VM | Get-Snapshot | Select VM,Name,Created,SizeGB
Get-VMHost | Select Name,ConnectionState,CpuUsageMhz,MemoryUsageGB
Get-Datastore | Select Name,FreeSpaceGB,CapacityGB
Get-VM NOME | Stop-VMGuest -Confirm:$false
```
