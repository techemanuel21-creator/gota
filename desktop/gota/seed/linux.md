# Linux: comandos e administração
Fonte: conhecimento base do Gota

## Sistema e processos
- uname -a; cat /etc/os-release; uptime; free -h; df -h; du -sh * | sort -h; lsblk; lscpu.
- top / htop; ps aux --sort=-%mem | head; kill PID; kill -9 PID (último recurso); pkill nome; nice/renice.
- systemd: systemctl status|start|stop|restart|enable|disable servico; systemctl list-units --failed; journalctl -u servico -f; journalctl -p err -b; journalctl --since "1 hour ago".
- Logs clássicos: /var/log/syslog ou /var/log/messages, /var/log/auth.log ou /var/log/secure, dmesg -T.

## Arquivos
- ls -lah; find / -name "*.log" -mtime -1; find . -type f -size +100M; grep -rn "texto" /pasta; grep -E regex; tail -f arquivo; less; sed -i 's/a/b/g' arquivo; awk '{print $1}'.
- Permissões: chmod 640 arq; chmod -R u+rwX,g+rX,o-rwx pasta; chown usuario:grupo arq; ls -l; umask; getfacl/setfacl.
- Compactar: tar -czvf backup.tar.gz pasta; tar -xzvf backup.tar.gz -C destino; zip -r a.zip pasta; unzip a.zip.
- Cópia/sincronização: rsync -avh --progress origem/ destino/ (--delete espelha, cuidado); scp arq usuario@host:/destino.

## Rede
- ip a; ip r; ip -s link; ss -tulpn (portas e processos); ss -ant state established; curl -I https://site; curl -v; wget; dig nome; nslookup; traceroute/mtr; ping -c 4.
- Firewall: ufw status; ufw allow 22/tcp; firewall-cmd --list-all; nft list ruleset; iptables -L -n -v.
- SSH: ssh usuario@host; ssh-keygen -t ed25519; ssh-copy-id usuario@host; /etc/ssh/sshd_config (PermitRootLogin no, PasswordAuthentication no, Port); systemctl restart sshd.
- Teste de porta: nc -zv host 443; nmap -sV host (somente em sistemas autorizados).

## Pacotes e usuários
- Debian/Ubuntu: apt update && apt upgrade; apt install pkg; apt remove pkg; dpkg -l | grep pkg.
- RHEL/Rocky/Alma: dnf install pkg; dnf update; rpm -qa | grep pkg.
- Usuários: useradd -m -s /bin/bash nome; passwd nome; usermod -aG sudo nome; id nome; last; lastb (logins falhos); who; sudo -l.
- Cron: crontab -e; formato min hora dia mes diasemana comando; "0 2 * * * /script.sh"; systemd timers como alternativa.

## Armazenamento
- LVM: pvs, vgs, lvs; lvextend -r -L +10G /dev/vg/lv; mount, umount; /etc/fstab (usar UUID: blkid); fsck só com a partição desmontada; smartctl -a /dev/sda (saúde do disco).
- RAID por software: cat /proc/mdstat; mdadm --detail /dev/md0.

## Docker rápido
- docker ps -a; docker logs -f contêiner; docker exec -it contêiner sh; docker stats; docker compose up -d / down; docker system df; docker system prune (remove não usados: cuidado).
