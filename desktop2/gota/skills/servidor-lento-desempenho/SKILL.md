---
name: servidor-lento-desempenho
description: Use quando um servidor Windows ou Linux estiver lento: CPU, memória, disco ou rede saturados.
keywords: servidor, lento, cpu, memória, disco, desempenho, load, latência, perfmon, top, iostat
---
# Servidor lento: onde está o gargalo

1. Descubra o recurso saturado:
   - **CPU**: Windows `Get-Counter '\Processor(_Total)\% Processor Time'`, Gerenciador de Tarefas; Linux `top`/`htop`, `uptime` (load acima do número de CPUs).
   - **Memória**: pouca RAM livre, paginação alta; Linux `free -h`, OOM em `dmesg`.
   - **Disco**: Windows latência `\PhysicalDisk(*)\Avg. Disk sec/Read` (acima de ~20 ms é ruim) e fila; Linux `iostat -x 1` (%util e await), `wa` alto no top.
   - **Rede**: banda, retransmissões, DNS lento.
2. Identifique o **processo** responsável (Resource Monitor, Process Explorer, `ps aux --sort=-%cpu`, `iotop`).
3. Se é VM: veja o host (CPU ready no VMware, overcommit, storage compartilhado, snapshots longos, ballooning).
4. Causas comuns: antivírus em varredura, backup rodando, atualização, loop de aplicação, consulta de banco pesada, disco quase cheio ou degradado (RAID em rebuild), vazamento de memória.
5. Corrija a causa, não só reinicie; meça de novo. Registre linha de base para comparar no futuro.
