# Redes: modelo, endereçamento, roteamento, switching, DNS/DHCP, firewall, VPN e diagnóstico
Fonte: conhecimento base do Gota

## Fundamentos
- **OSI** (física, enlace, rede, transporte, sessão, apresentação, aplicação) e **TCP/IP**. Ethernet/MAC (enlace), IP (rede), TCP/UDP (transporte).
- **IPv4**: máscara/CIDR (/24 = 255.255.255.0 = 254 hosts; /25 126; /26 62; /27 30; /28 14; /30 2), faixas privadas RFC1918: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16; APIPA 169.254.x.x (DHCP falhou); loopback 127.0.0.1. **IPv6**: /64 por LAN, link-local fe80::/10, SLAAC.
- **Portas comuns**: 20/21 FTP, 22 SSH, 23 Telnet, 25 SMTP, 53 DNS, 67/68 DHCP, 80 HTTP, 88 Kerberos, 110 POP3, 123 NTP, 135 RPC, 137-139 NetBIOS, 143 IMAP, 161/162 SNMP, 389 LDAP, 443 HTTPS, 445 SMB, 465/587 SMTP seguro, 514 syslog, 636 LDAPS, 993/995 IMAPS/POP3S, 1433 SQL Server, 1521 Oracle, 3306 MySQL, 3389 RDP, 5432 PostgreSQL, 5985/5986 WinRM, 6379 Redis, 8080 proxy/alt-HTTP, 9200 Elasticsearch, 27017 MongoDB.

## Switching
- **VLAN** (802.1Q), **trunk** (tagged) x **access** (untagged), **native VLAN**, **STP/RSTP/MSTP** (evita loops; root bridge; portfast + BPDU guard nas portas de acesso), **LACP/802.3ad** (agregação), **port-security**, **DHCP snooping**, **DAI**, **storm-control**, **PoE**, **QoS**, **jumbo frames** (MTU 9000 ponta a ponta, p.ex. iSCSI/vMotion), **spanning tree loop** causa tempestade de broadcast (rede inteira lenta, CPU de switch 100%).
- Diagnóstico Cisco-like: `show interfaces status`, `show interface Gi1/0/1` (erros CRC, collisions, drops), `show mac address-table`, `show vlan brief`, `show spanning-tree`, `show etherchannel summary`, `show logging`.

## Roteamento
- **Estático**, **OSPF** (IGP link-state, áreas, LSAs), **EIGRP**, **BGP** (entre ASNs, eBGP/iBGP, atributos: local-pref, AS-path, MED), **VRRP/HSRP** (gateway redundante), **NAT/PAT**, **SD-WAN**. Tabela de rotas: Windows `route print`, Linux `ip route`, equipamentos `show ip route`. Rota mais específica vence (longest prefix match). Gateway padrão incorreto, rota de retorno ausente e NAT assimétrico explicam muitos "vai mas não volta".

## DNS, DHCP, NTP
- **DNS**: A, AAAA, CNAME, MX, TXT, NS, PTR, SRV (AD usa SRV); zonas diretas/reversas; encaminhadores; cache. Testes: `nslookup nome servidor`, `dig +short nome @servidor`, `Resolve-DnsName`, `ipconfig /flushdns`, `/displaydns`. Muita falha é DNS: servidor errado na placa, domínio AD apontando para DNS público.
- **DHCP**: DORA (Discover, Offer, Request, Ack); escopo, reservas, exclusões, relay (ip helper); conflito de IP; 169.254 = sem DHCP. `ipconfig /release /renew`, `dhclient`, `Get-DhcpServerv4Lease`.
- **NTP**: horário errado quebra Kerberos (tolerância 5 min), certificados, backup, logs. `w32tm /query /status`, `/resync`, `chronyc tracking`.

## Firewall, proxy, VPN
- Firewall stateful: regras ordem, zonas, NAT, inspeção; **NGFW** (aplicação/IPS/URL); WAF para web; **Windows Firewall**: `netsh advfirewall`, `Get-NetFirewallRule`; Linux `iptables -L -n -v`, `nft list ruleset`, `ufw status`, `firewall-cmd --list-all`.
- **VPN**: IPsec (IKEv1/IKEv2, fase 1/fase 2, PSK/certificado, NAT-T UDP 4500, ESP 50), SSL-VPN, OpenVPN, WireGuard (UDP, chaves públicas). Falhas comuns: relógio, PSK, propostas diferentes, ACL/selector (tráfego interessante), MTU/MSS (use clamping ~1350-1400), NAT duplo, firewall bloqueando UDP 500/4500.
- **Proxy/reverse proxy/Load balancer**: nginx, HAProxy, F5; health checks; sticky sessions; TLS offload.

## Wi-Fi
2,4 GHz (3 canais sem sobreposição 1/6/11, mais alcance), 5/6 GHz (mais velocidade). WPA2/WPA3, 802.1X (RADIUS), roaming, canal sobreposto, interferência, densidade de clientes e cobertura (RSSI > -67 dBm para voz).

## Método de diagnóstico (camada a camada)
1. Física: cabo, link, LEDs, `ipconfig /all`, erros de interface.
2. Enlace: VLAN correta, MAC aprendido, ARP (`arp -a`).
3. Rede: IP/máscara/gateway, `ping` gateway, ping IP externo (8.8.8.8), `tracert`/`traceroute`/`mtr`/`pathping`.
4. DNS: ping por nome, `nslookup`.
5. Transporte: porta aberta? Windows `Test-NetConnection host -Port 443`, Linux `nc -vz host 443`, `ss -tulpn`, `netstat -ano`.
6. Aplicação: logs, certificado (`openssl s_client -connect host:443`), `curl -v`.
- Captura: Wireshark/`tcpdump -i eth0 host X and port Y -w arq.pcap`, `pktmon` no Windows. Filtros úteis: `tcp.analysis.retransmission`, `dns`, `tls.handshake`.
- Lentidão: `iperf3 -c servidor`, duplex/velocidade negociada, erros CRC, bufferbloat, MTU/fragmentação (`ping -f -l 1472`), CPU do firewall, DNS lento, QoS.
- Monitoramento: SNMP v3, NetFlow/sFlow, syslog, Zabbix/PRTG/LibreNMS, Grafana.

## Segurança de rede (resumo)
Segmentação (VLANs, zonas, microssegmentação), menor privilégio entre segmentos, gerência fora de banda, desativar protocolos legados (Telnet, SMBv1, TLS 1.0/1.1, SNMP v1/v2c), ACLs, 802.1X/NAC, IDS/IPS, DNS filtering, logs centralizados (SIEM), patch de firmware, backup de configuração de equipamentos.
