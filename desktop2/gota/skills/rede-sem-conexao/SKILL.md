---
name: rede-sem-conexao
description: Use quando um computador ou servidor não acessa a rede, a internet ou um serviço (sem conexão, DNS falhando, porta fechada).
keywords: rede, internet, sem conexão, dns, gateway, ping, porta, firewall, ipconfig, nslookup, tracert, test-netconnection
---
# Sem rede ou sem acesso a um serviço

1. IP: `ipconfig /all`. Confira IP (169.254.x.x indica falha de DHCP), máscara, gateway e DNS.
2. Gateway: `ping <gateway>`. Sem resposta indica problema local (cabo, Wi-Fi, VLAN, switch).
3. Internet por IP: `ping 1.1.1.1`. Se responde por IP mas não por nome, o problema é DNS.
4. DNS: `nslookup exemplo.com` e `Resolve-DnsName exemplo.com`. Limpe o cache com `ipconfig /flushdns` e teste outro servidor: `nslookup exemplo.com 1.1.1.1`.
5. Serviço específico: `Test-NetConnection servidor -Port 443` (TcpTestSucceeded precisa ser True). Se falhar, suspeite do firewall local (`Get-NetFirewallProfile`), do firewall da rede ou do serviço parado no destino.
6. Caminho: `tracert servidor`. O ponto onde para de responder é o que deve ser investigado.
7. Último recurso, que causa uma breve queda: `netsh winsock reset` e `netsh int ip reset`, e reinicie o computador.
