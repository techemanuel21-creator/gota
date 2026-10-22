---
name: rede-lenta
description: Use quando a rede estiver lenta, com perda de pacotes, atraso ou transferências abaixo do esperado.
keywords: rede, lenta, latência, perda de pacotes, throughput, duplex, mtu, dns, switch, banda
---
# Rede lenta: diagnóstico por camadas

1. **Escopo**: um usuário, uma VLAN ou todos? Só um serviço ou tudo? Desde quando?
2. **Física/enlace**: velocidade e duplex negociados (esperado 1G/10G full), erros CRC, collisions e drops na interface do switch, cabo, SFP, loop de STP (broadcast storm), agregação LACP desbalanceada.
3. **Latência e perda**: `ping -n 50 gateway`, `pathping`/`mtr` até o destino; veja em qual salto começa.
4. **DNS lento**: `nslookup` demora? Servidor DNS errado ou inalcançável na placa dá lentidão em tudo.
5. **MTU**: `ping -f -l 1472 destino` (Windows) ou `ping -M do -s 1472` (Linux); VPN costuma exigir MSS menor.
6. **Vazão**: `iperf3 -s` em um lado e `iperf3 -c servidor` no outro; compare com o esperado.
7. **Camada superior**: CPU do firewall, QoS, proxy, antivírus inspecionando tráfego, retransmissões TCP no Wireshark, SMB signing/criptografia.
8. Corrija o gargalo encontrado e meça de novo para provar a melhora.
