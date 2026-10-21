---
name: cisco-configurar-portas-e-vlans
description: Use quando o pedido for configurar portas, VLANs, trunks, voice VLAN ou resetar portas de um switch Cisco (IOS ou IOS-XE).
keywords: cisco, switch, vlan, trunk, access, voice vlan, porta, portas, interface, configurar, resetar, default interface, switchport, ios, catalyst
---
# Configurar portas e VLANs em switch Cisco

Siga o pedido À RISCA. Não invente VLANs, nativas, listas permitidas, portas extras nem comandos que o pedido não mandou.

1. **Monte a tabela do pedido** antes de escrever: cada linha "porta; nome" é a *etiqueta* da porta (vira `description`), o grupo diz o modo (access, trunk), a VLAN e a voice VLAN.
2. **Ordem do script**: `configure terminal` → criar só as VLANs que o pedido diz que não existem (e a voice VLAN se for nova, com `vlan N` + `name`) → resetar **somente** as portas listadas → configurar cada grupo → `end` → `write memory` (ou avisar que falta salvar).
3. **Resetar só as portas pedidas**: `default interface range GigabitEthernet1/0/1-37` (um comando por faixa contínua listada). Portas fora da lista (por exemplo a 38) não entram em nenhum comando. Nunca use `erase startup-config`, `reload` nem `default running-config` se o pedido é só de algumas portas.
4. **Access**: `switchport mode access` e `switchport access vlan N`. Com voice VLAN: acrescente `switchport voice vlan N`. VLAN 1 em access é o padrão, mas escreva o comando pedido.
5. **Trunk**: `switchport mode trunk`. Em IOS antigo (3560/3750) é preciso `switchport trunk encapsulation dot1q` antes; em 2960, 3650, 9200 não. **Não restrinja** `allowed vlan` nem mude a `native vlan` se o pedido não falou: o padrão permite todas as VLANs. Só sugira restringir como observação opcional, fora do script.
6. **Descrições**: depois do reset, `description` em cada interface com a etiqueta exata do pedido. Quando cada porta tem nome diferente (ex.: 41 Link02, 42 Link01FW01, 43 Link01FW02), configure uma interface por vez; quando o nome é igual, use `interface range`.
7. **Nome das interfaces**: assuma `GigabitEthernet1/0/N` (switch empilhável/48 portas) e diga a suposição; em switch de 1 chassi pode ser `GigabitEthernet0/N`. Confirme com `show ip interface brief`.
8. **Formato da resposta**: bloco de código com o script limpo (comentários `!` curtos por bloco, sem avisos longos), depois no máximo 3 observações curtas (suposições, risco, como verificar).
9. **Verificar**: `show vlan brief`, `show interfaces trunk`, `show interfaces status`, `show running-config interface GigabitEthernet1/0/41`.
10. **Riscos**: `default interface` apaga descrição, portfast, port-security e tudo da porta; se a sessão de gerência passa por uma dessas portas, a conexão cai. Faça antes `show running-config` e guarde a saída.