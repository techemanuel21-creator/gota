# Infraestrutura de TI: redes, servidores, virtualização e armazenamento
Fonte: conhecimento base do Gota

## Redes
- Modelo OSI: 1 física, 2 enlace (Ethernet, VLAN, MAC), 3 rede (IP, roteamento, ICMP), 4 transporte (TCP/UDP), 5-7 sessão/apresentação/aplicação.
- IP e máscara: /24 = 255.255.255.0 = 254 hosts; /16 = 65.534 hosts; /30 = 2 hosts (enlace ponto a ponto). Faixas privadas: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16. APIPA 169.254.x.x indica que o DHCP falhou.
- Portas comuns: 20/21 FTP, 22 SSH, 23 Telnet, 25 SMTP, 53 DNS, 67/68 DHCP, 80 HTTP, 88 Kerberos, 110 POP3, 123 NTP, 135 RPC, 137-139 NetBIOS, 143 IMAP, 161/162 SNMP, 389 LDAP, 443 HTTPS, 445 SMB, 465/587 SMTP seguro, 636 LDAPS, 993 IMAPS, 1433 SQL Server, 3306 MySQL, 3389 RDP, 5432 PostgreSQL, 5985/5986 WinRM.
- Problemas típicos: sem internet mas com IP -> testar gateway, depois 8.8.8.8, depois nome (DNS). Lentidão: duplex/negociação, loops (STP), cabo ruim (erros na interface), saturação (iftop, Get-NetAdapterStatistics). Wi-Fi: canal congestionado, 2,4 GHz vs 5 GHz, sinal abaixo de -70 dBm ruim.
- DHCP: concessão, escopo esgotado, reservas; DNS: registros A, AAAA, CNAME, MX, TXT, NS, SOA, PTR; TTL e cache; nslookup/dig para testar.
- Active Directory: domínio, controladores, FSMO (5 funções), replicação (repadmin /replsummary), DNS integrado, GPO (gpupdate, gpresult), Kerberos exige horário sincronizado (diferença máxima padrão de 5 minutos), contas bloqueadas (evento 4740).

## Servidores e virtualização
- Hyper-V, VMware vSphere/ESXi, Proxmox VE, KVM: hypervisor roda VMs; snapshots não são backup (crescem e degradam desempenho); alocar vCPU/RAM sem exagero (overcommit com cuidado); drivers paravirtualizados (VMware Tools, Integration Services, virtio).
- Alta disponibilidade: cluster, vMotion/live migration, HA reinicia VMs em outro host, DRS balanceia carga. Armazenamento compartilhado: iSCSI, FC, NFS, SMB3, vSAN, S2D.
- Monitoramento: CPU, memória, latência de disco (acima de 20-30 ms preocupa), rede, espaço livre (alertar com 80% e 90%), eventos de hardware (iLO/iDRAC), temperatura. Ferramentas: Zabbix, Prometheus+Grafana, PRTG, Nagios.

## Armazenamento e RAID
- RAID 0 (sem redundância), 1 (espelho), 5 (paridade, tolera 1 disco), 6 (tolera 2), 10 (espelho+stripe, bom para desempenho). RAID não é backup. Discos grandes demoram a reconstruir: preferir RAID 6/10.
- IOPS, latência e vazão são métricas diferentes; SSD/NVMe para banco de dados; SMART (smartctl, Get-PhysicalDisk | Get-StorageReliabilityCounter) para saúde.

## Backup e recuperação (conceitos)
- RPO = quanto de dado se aceita perder; RTO = quanto tempo se aceita ficar fora. Full, incremental (só mudanças desde o último), diferencial (mudanças desde o último full), synthetic full, forever forward incremental, reverse incremental.
- 3-2-1-1-0, imutabilidade (repositório Linux hardened, S3 object lock), criptografia do backup e guarda da senha, testes de restauração, janela de backup, retenção e GFS (diário, semanal, mensal, anual).
