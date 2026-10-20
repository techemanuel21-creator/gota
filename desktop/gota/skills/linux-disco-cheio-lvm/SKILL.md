---
name: linux-disco-cheio-lvm
description: Use quando um servidor Linux estiver sem espaço em disco, sem inodes ou precisar ampliar LVM/filesystem.
keywords: linux, disco cheio, df, inodes, lvm, lvextend, xfs_growfs, resize2fs, logs, docker
---
# Linux: disco cheio e ampliação de LVM

1. `df -hT` e `df -i`: falta espaço ou **inodes**? Qual ponto de montagem?
2. Encontre quem ocupa: `du -xh / --max-depth=1 | sort -h | tail` e aprofunde (ou `ncdu /`). Locais comuns: `/var/log`, `/var/lib/docker`, `/tmp`, caches de pacotes, backups locais.
3. Espaço "sumido": arquivo apagado ainda aberto: `lsof +L1` (reinicie o processo dono).
4. Limpeza segura: `journalctl --vacuum-size=500M`, rotacione logs, `apt clean` ou `dnf clean all`, `docker system df` e `docker system prune` (confirme o que será removido).
5. Ampliar: aumente o disco na virtualização, `growpart /dev/sda 2`, `pvresize /dev/sda2`, `lvextend -r -l +100%FREE /dev/vg/lv` (o `-r` cresce o filesystem; em XFS use `xfs_growfs /ponto`, em ext4 `resize2fs`).
6. Evite repetir: alertas a 80%, retenção de logs, monitoramento do crescimento.
