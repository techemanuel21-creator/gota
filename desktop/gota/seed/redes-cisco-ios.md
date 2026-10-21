# Cisco IOS / IOS-XE: switching, VLANs, trunks, voz, STP e diagnóstico
Fonte: conhecimento base do Gota

## Modos e salvar
- `enable` (privilegiado), `configure terminal` (global), `interface X` (interface), `end`/`Ctrl+Z` volta ao privilegiado. Salvar: `write memory` ou `copy running-config startup-config`. `show running-config` (ativa), `show startup-config` (salva).
- Nomes de interface: `GigabitEthernet1/0/N` (stack/48p), `GigabitEthernet0/N` (1 chassi), `TenGigabitEthernet1/1/N`. Faixas: `interface range Gi1/0/1-12, Gi1/0/20`. Abreviações aceitas (`int gi1/0/1`).
- `default interface X` ou `default interface range ...` devolve a(s) porta(s) ao padrão de fábrica (apaga description, switchport, portfast, security). Só as portas indicadas; não toca no resto.

## VLANs, access, voz e trunk
```
vlan 900
 name LINKS
interface GigabitEthernet1/0/41
 description Link02
 switchport mode access
 switchport access vlan 900
interface range GigabitEthernet1/0/13-27
 switchport mode access
 switchport access vlan 1
 switchport voice vlan 13        ! telefone IP etiquetado na VLAN 13, PC na access
interface range GigabitEthernet1/0/28-37
 switchport mode trunk           ! em IOS antigo: switchport trunk encapsulation dot1q antes
 switchport trunk native vlan 1  ! opcional
 switchport trunk allowed vlan 1,13,900   ! opcional; sem isso permite todas
```
- VLAN precisa existir para ser usada (criar com `vlan N`); VLAN 1 é padrão e não se apaga. Voice VLAN também deve existir. Em modo transparente/VTP: `show vtp status`; VLANs de 1 a 1005 normais, 1006-4094 estendidas (precisa VTP transparent/v3).
- Trunk: encapsulamento 802.1Q (tag), native VLAN sem tag (precisa igual nas duas pontas), `allowed vlan` (add/remove com `switchport trunk allowed vlan add 20`). `switchport nonegotiate` desliga DTP. Negociação DTP: `dynamic desirable/auto`.
- Portas de acesso a PC: `spanning-tree portfast` + `spanning-tree bpduguard enable`. Portas só access: `switchport mode access` + `switchport nonegotiate`.
- Segurança de porta: `switchport port-security`, `... maximum 2`, `... violation restrict`, `... mac-address sticky`. DHCP snooping: `ip dhcp snooping`, `ip dhcp snooping vlan 10`, portas confiáveis com `ip dhcp snooping trust`. `ip arp inspection vlan 10`, `ip verify source`.
- Agregação: `channel-group 1 mode active` (LACP) / `desirable` (PAgP) / `on`; interface `Port-channel1`; `show etherchannel summary`.
- Descrição e desligar: `description texto`, `shutdown` / `no shutdown`. Velocidade: `speed 1000`, `duplex full` (preferir auto).
- PoE: `power inline auto|never`, `show power inline`.

## STP
- Modos: `spanning-tree mode rapid-pvst` (recomendado). Raiz: `spanning-tree vlan 1 root primary`. `show spanning-tree`, `show spanning-tree summary`, portas em `err-disabled` por bpduguard: `show interfaces status err-disabled`, depois `shutdown` + `no shutdown`; recuperação automática: `errdisable recovery cause bpduguard`.

## Comandos de diagnóstico
`show ip interface brief`, `show interfaces status`, `show interfaces Gi1/0/1` (erros CRC/input errors, duplex), `show vlan brief`, `show interfaces trunk`, `show mac address-table [interface Gi1/0/1]`, `show cdp neighbors detail`, `show lldp neighbors`, `show logging`, `show version`, `show inventory`, `show environment`, `show processes cpu sorted`, `show tech-support`. Testes: `ping`, `traceroute`, `show arp`, `show ip route`.

## Roteamento e L3 básico
- `ip routing` (switch L3), SVI: `interface vlan 10` + `ip address 10.0.10.1 255.255.255.0` + `no shutdown`. Rota estática: `ip route 0.0.0.0 0.0.0.0 192.168.1.1`. OSPF: `router ospf 1`, `network 10.0.0.0 0.0.0.255 area 0`, `show ip ospf neighbor`. DHCP relay: `ip helper-address 10.0.0.5`. HSRP: `standby 1 ip 10.0.10.254`, `standby 1 priority 110`, `standby 1 preempt`.
- ACL: `ip access-list extended NOME`, `permit tcp any host 10.0.0.10 eq 443`, `deny ip any any log`, aplicar `ip access-group NOME in` na interface. NAT: `ip nat inside source list 1 interface Gi0/0 overload` + `ip nat inside/outside` nas interfaces.

## Gerência e segurança do equipamento
`hostname`, `enable secret`, `service password-encryption`, `username admin privilege 15 secret ...`, SSH: `ip domain-name x`, `crypto key generate rsa modulus 2048`, `line vty 0 15` + `transport input ssh` + `login local`, `ip ssh version 2`; desativar telnet/http: `no ip http server`; `ntp server 10.0.0.1`; `logging host 10.0.0.9`; SNMPv3; `banner motd`. Backup: `copy running-config tftp:`, `archive`.

## Problemas comuns
- Porta em err-disabled (bpduguard, port-security, link-flap, UDLD): ver `show interfaces status err-disabled`, corrigir a causa e reativar.
- Trunk que não passa VLAN: `allowed vlan`, VLAN inexistente no outro lado, native VLAN diferente (mensagem `%CDP-4-NATIVE_VLAN_MISMATCH`).
- Telefone sem voz: `switchport voice vlan`, CDP/LLDP-MED, PoE, DHCP na VLAN de voz.
- Lentidão: duplex mismatch (collisions/late collisions), erros CRC, loop de STP, CPU alta (`show processes cpu`), storm-control.
- Recuperação de senha: segurar o botão MODE ao ligar (switch), `flash_init`, `rename flash:config.text flash:config.old`, `boot`.