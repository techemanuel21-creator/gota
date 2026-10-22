# Nutanix: AHV, Prism, CVM, AOS, cluster e diagnóstico
Fonte: conhecimento base do Gota (confirme na documentação portal.nutanix.com para a versão em uso)

## Arquitetura
- **HCI**: cada nó roda o hypervisor (**AHV**, ou ESXi/Hyper-V) e uma **CVM** (Controller VM) que serve o armazenamento distribuído (**AOS**, Distributed Storage Fabric). Dados replicados entre nós por **RF2/RF3** (replication factor).
- Componentes: **Prism Element** (gestão de um cluster, https://IP-CVM:9440), **Prism Central** (multi-cluster, políticas, Calm, Flow), **Storage Pools** e **Containers** (compressão, dedup, erasure coding), **Acropolis (acli)**, **Cassandra** (metadados), **Zookeeper**, **Curator** (limpeza/balanceamento), **Stargate** (I/O), **Medusa**, **Pithos**, **Genesis** (gerencia serviços), **Cerebro** (proteção de dados/snapshots), **Stargate**, **Prism/Mercury**.
- **Data protection**: snapshots, **Protection Domains** (legado) e **Protection Policies/Recovery Plans** (Prism Central), replicação assíncrona/NearSync/síncrona, Metro Availability. Backup de terceiros (Veeam com plugin AHV) usa snapshots/API.
- Rede: AHV usa Open vSwitch (**br0**, bonds **br0-up**); VLAN por rede virtual; mantenha CVMs e hosts na mesma subnet de gerência, rede de storage entre CVMs estável.

## Comandos (rodar na CVM via SSH como `nutanix`)
```sh
cluster status                       # serviços de cada CVM (todos devem estar UP)
ncli cluster info                    # nome, versão, redundância
ncli host list ; ncli vm list
ncc health_checks run_all            # checagem de saúde completa (gera relatório em /home/nutanix/data/logs/ncc-output-latest.log)
ncc health_checks network_checks run_all
acli vm.list ; acli vm.get NOME ; acli vm.on NOME ; acli vm.off NOME
acli net.list
allssh "df -h"                       # espaço em todas as CVMs
genesis status ; cluster start        # iniciar serviços se parados (cuidado em produção)
nodetool -h localhost ring            # estado do anel Cassandra
ncli disk list ; ncli storage-pool list ; ncli container list
curator_cli display_data_reduction_report
ncli alerts ls                        # alertas
```
Logs: `/home/nutanix/data/logs/` (genesis.out, stargate.INFO, cassandra*, curator*, acropolis.out), no host AHV `/var/log/` e `virsh list --all` (`virsh` no host AHV, não use para mudar VMs gerenciadas pelo Acropolis).

## Manutenção e atualização
- **LCM** (Life Cycle Manager) atualiza AOS, AHV, firmware, NCC, Foundation. Rode `ncc health_checks run_all` antes; resolva alertas; faça uma atualização por vez; **rolling upgrade** reinicia um nó por vez (precisa de capacidade livre para tolerar um nó fora).
- Colocar um host em manutenção: migrar VMs (Prism ou `acli host.enter_maintenance_mode`), depois reiniciar; só tire outro nó depois de o cluster voltar a **Data Resiliency OK**.
- Nunca desligue 2 nós ao mesmo tempo em RF2: risco de perda de dados/indisponibilidade.

## Problemas frequentes
- **"Data resiliency" não OK**: nó/disco fora; veja Prism > Home > Data Resiliency Status; reconstrução (rebuild) em andamento consome I/O; espere antes de novas manutenções.
- **CVM down**: VMs do host continuam (acesso via CVM de outro nó), mas há degradação; reinicie a CVM (`virsh start NTNX-...-CVM` no host AHV) após verificar causa (disco, memória, rede).
- **Alerta de espaço**: >75% no storage pool exige ação; limpar snapshots antigos, VMs órfãs, reduzir RF onde permitido, adicionar nós; o espaço necessário para tolerar falha de um nó deve ser reservado.
- **Disco falho**: troca a quente pelo Prism (Hardware > Diagram > Disk); o cluster reconstrói; validar `ncli disk list`.
- **Latência alta**: ver Prism Analysis (IOPS, latência, CPU ready equivalente); VMs "barulhentas"; rede 10/25 GbE saturada; throttling; hot-tier SSD cheio.
- **VM não liga**: sem memória livre no host, imagem/ISO ausente, vNIC sem rede, restrição de afinidade, host em manutenção.
- **Prism inacessível**: serviço `prism` ou `genesis` parado; VIP do cluster (Cluster Virtual IP) mal configurado; certificado; DNS/NTP incorretos (NTP errado quebra serviços).
- **Replicação atrasada**: banda WAN, remote site mal configurado, snapshots em fila.

## Boas práticas
NTP/DNS corretos e redundantes; N+1 de capacidade; monitorar NCC semanalmente; manter Pulse ativo; backup externo mesmo com snapshots; firmware e AOS na matriz de compatibilidade; LACP/active-backup consistente com o switch; hosts e CVMs em VLAN de gerência protegida; contas locais e MFA/SSO via Prism Central.
