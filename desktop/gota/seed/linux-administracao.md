# Linux: administração, diagnóstico, rede, serviços, armazenamento e segurança
Fonte: conhecimento base do Gota

## Diagnóstico rápido do sistema
```sh
uptime ; free -h ; df -hT ; df -i          # carga, memória, discos, inodes
top / htop ; ps aux --sort=-%mem | head    # processos
vmstat 1 5 ; iostat -x 1 3 ; sar -u 1 3    # CPU, I/O
journalctl -p err -b                       # erros desde o boot
journalctl -u SERVICO --since "1 hour ago" -f
dmesg -T | tail -50 ; dmesg -T | grep -i -E 'error|fail|oom|I/O'
last -x | head ; who ; w
ss -tulpn ; ip -br a ; ip r ; resolvectl status
lsof -i :80 ; lsof +L1                      # quem usa a porta; arquivos apagados ainda abertos
```
- **Load average** acima do número de CPUs = fila de execução ou I/O. `wa` alto no top = I/O. **OOM killer**: `dmesg | grep -i 'killed process'`; veja swap, limites de cgroup, vazamento de memória.

## systemd (serviços)
`systemctl status X`, `start/stop/restart/reload`, `enable --now`, `is-active`, `systemctl --failed`, `journalctl -xeu X`, `systemctl cat X`, `systemctl daemon-reload` após mudar unit. Serviço falhando: ver código de saída (`Main PID ... status=`), permissão/SELinux, porta ocupada, arquivo de configuração (teste com `nginx -t`, `apachectl configtest`, `sshd -t`), variáveis de ambiente, dependências (`After=`), limites (`LimitNOFILE`), `Restart=on-failure`. Timers substituem cron: `systemctl list-timers`.

## Pacotes
Debian/Ubuntu: `apt update && apt upgrade`, `apt install`, `dpkg -l | grep`, `apt-cache policy`, `unattended-upgrades`. RHEL/Rocky/Alma/Fedora: `dnf install/update`, `rpm -qa`, `dnf history`, `subscription-manager`. SUSE: `zypper`. Arch: `pacman`. Contêineres e snaps: `snap`, `flatpak`.

## Armazenamento, LVM, RAID
```sh
lsblk -f ; blkid ; fdisk -l ; parted -l
pvs ; vgs ; lvs ; pvdisplay
lvextend -r -L +10G /dev/vg/lv            # -r redimensiona o filesystem junto
growpart /dev/sda 1 ; resize2fs /dev/sda1 # ext4 ;  xfs_growfs /ponto  (xfs)
mount -a ; findmnt ; cat /etc/fstab        # UUID no fstab, opção nofail em discos opcionais
mdadm --detail /dev/md0 ; cat /proc/mdstat
smartctl -a /dev/sda ; fsck -f /dev/sdb1   # fsck só desmontado
du -xh / --max-depth=1 | sort -h | tail ; ncdu /
```
Disco cheio: verificar `df -h` e `df -i` (inodes), arquivos apagados mas abertos (`lsof +L1`), logs (`journalctl --vacuum-size=500M`), `/var/log`, docker (`docker system df`, `docker system prune`), caches de pacotes.

## Rede
`ip a`, `ip r`, `ip link set dev eth0 up`, NetworkManager (`nmcli`), netplan (`/etc/netplan/*.yaml`, `netplan apply`), `/etc/resolv.conf` e systemd-resolved, `/etc/hosts`, `ping`, `traceroute`, `mtr`, `ss`, `nc -vz host porta`, `curl -v`, `tcpdump`, `iptables/nftables/firewalld/ufw`. Bonding/team, VLAN (`ip link add link eth0 name eth0.100 type vlan id 100`), bridge para KVM.

## Usuários, permissões, sudo, SSH
- `useradd -m -s /bin/bash usuario`, `passwd`, `usermod -aG grupo`, `chage -l`, `id`, `/etc/passwd`, `/etc/shadow`, `visudo`, `sudo -l`. Permissões `rwx` (4,2,1): `chmod 640`, `chown u:g`, bits especiais (setuid, setgid, sticky), ACL (`setfacl/getfacl`), umask.
- SSH: `~/.ssh/authorized_keys` (permissões 700/600), `sshd_config` (`PermitRootLogin no`, `PasswordAuthentication no`), `ssh -vvv` para depurar, `ssh-keygen -t ed25519`, `ssh-copy-id`, túneis `-L/-R/-D`, `scp/rsync -avz`.
- **SELinux**: `getenforce`, `ausearch -m avc -ts recent`, `restorecon -Rv`, `setsebool -P`, `semanage fcontext` (não desligar; ajustar contexto). **AppArmor**: `aa-status`.

## Automação e arquivos
`cron` (`crontab -e`; min hora dia mês diasemana), `at`, `systemd timers`, `rsync`, `tar czf/xzf`, `find / -size +1G`, `grep -R`, `awk`, `sed`, `sort | uniq -c`, `xargs`, `tee`, redirecionamento. Shell: `set -euo pipefail`, aspas em variáveis, `trap`.

## Virtualização e contêineres em Linux
**KVM/QEMU/libvirt** (`virsh list --all`, `virt-install`, `virsh snapshot-*`), **Proxmox VE** (cluster corosync, `qm`, `pct`, ZFS/Ceph), **Docker** (`docker ps -a`, `logs`, `exec -it`, `compose up -d`, volumes, redes), **Kubernetes** (`kubectl get pods -A`, `describe`, `logs`, `rollout`, eventos, CrashLoopBackOff = ver logs/ probes/ recursos, ImagePullBackOff = imagem/credencial, Pending = recursos/taint/PVC), **Podman**, **LXC**.

## Serviços comuns
nginx/Apache (vhost, proxy_pass, certificados, `nginx -t`), PostgreSQL/MySQL/MariaDB (usuários, backup `pg_dump`/`mysqldump`, replicação, `max_connections`), Samba/NFS, Postfix/Dovecot, BIND/dnsmasq/unbound, chrony, rsyslog, fail2ban, Certbot/Let's Encrypt (renovação, porta 80/443, DNS-01).

## Boot e recuperação
GRUB (editar linha com `e`, `init=/bin/bash` ou `rd.break` em RHEL para resetar senha root), modo de recuperação (`systemctl rescue`), `fsck`, initramfs (`dracut -f`, `update-initramfs -u`), kernel antigo no GRUB, `journalctl -b -1` (boot anterior), `/etc/fstab` com erro leva a emergency mode: comente a linha ruim.
