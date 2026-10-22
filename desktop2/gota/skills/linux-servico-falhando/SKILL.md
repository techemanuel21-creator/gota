---
name: linux-servico-falhando
description: Use quando um serviço no Linux (systemd) falha, reinicia em loop ou não sobe.
keywords: linux, systemd, systemctl, journalctl, serviço, falhou, failed, reinicia, nginx, apache, ssh
---
# Serviço do Linux que falha

1. Estado: `systemctl status nome.service -l --no-pager`.
2. Logs do serviço: `journalctl -u nome.service -n 100 --no-pager` (desde o boot, acrescente `-b`).
3. A configuração é válida? Exemplos: nginx `nginx -t`, apache `apachectl configtest`, sshd `sshd -t`.
4. Recursos: porta ocupada `ss -ltnp | grep :PORTA`; disco e inodes `df -h` e `df -i`; memória `free -h` e `dmesg -T | grep -i -E 'oom|killed'`.
5. Permissões e SELinux: `ls -l`, `journalctl | grep -i denied` e `getenforce`.
6. Depois de corrigir: `systemctl daemon-reload` (se mudou a unit), `systemctl restart nome.service` e, para subir no boot, `systemctl enable nome.service`.
