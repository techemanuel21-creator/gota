# Cibersegurança: fundamentos, resposta a incidentes e hardening
Fonte: conhecimento base do Gota

## Princípios
- Tríade CIA: confidencialidade, integridade, disponibilidade. Menor privilégio, defesa em profundidade, segmentação de rede, patching, MFA, logs centralizados, backups imutáveis e testados.
- Frameworks: NIST CSF (identificar, proteger, detectar, responder, recuperar), CIS Controls, ISO 27001, MITRE ATT&CK (táticas e técnicas de atacantes), OWASP Top 10 (aplicações web).

## Resposta a incidentes (NIST): preparação → detecção e análise → contenção, erradicação e recuperação → lições aprendidas
- Suspeita de ransomware: isolar a máquina da rede (desconectar cabo/Wi-Fi, não desligar se quiser preservar memória), identificar o escopo, preservar logs, NÃO pagar sem avaliação jurídica, restaurar de backup limpo (verificar que o backup não está comprometido), trocar credenciais, procurar persistência (tarefas agendadas, serviços novos, chaves Run, contas novas).
- Conta comprometida: revogar sessões e tokens, redefinir senha, exigir MFA, revisar regras de caixa de entrada e encaminhamentos, olhar logons 4624/4625 e origens estranhas.
- Indicadores comuns: processos filhos estranhos de office/navegador (powershell -enc, cmd /c), muitas falhas 4625 seguidas de 4624 (força bruta), log limpo (1102), serviços novos (7045), RDP exposto (3389), contas novas no grupo administradores.

## Hardening Windows
- Aplicar atualizações, BitLocker, Defender ativo com proteção em tempo real, ASR rules, SmartScreen, desabilitar SMBv1 (Disable-WindowsOptionalFeature -Online -FeatureName SMB1Protocol), LAPS para senha de administrador local, não usar admin no dia a dia, RDP somente via VPN/RD Gateway com NLA e MFA, auditar com a política de auditoria avançada, restringir PowerShell (Constrained Language/AppLocker/WDAC), LLMNR e NetBIOS desativados quando possível.
## Hardening Linux
- SSH com chave e sem root/senha, fail2ban, firewall com política padrão negar, atualizações automáticas de segurança, desativar serviços sem uso, auditd, SELinux/AppArmor ativo, permissões 600/700 em segredos, sudo com registro.

## Redes
- Portas expostas à internet que merecem atenção: 3389 RDP, 445 SMB, 22 SSH, 23 Telnet, 5900 VNC, 1433 SQL Server, 3306 MySQL, 5432 PostgreSQL, 6379 Redis, 9200 Elasticsearch, 2375 Docker sem TLS. Verificar com ss -tulpn (Linux) ou Get-NetTCPConnection -State Listen (Windows).
- Segmentar VLANs (usuários, servidores, gestão, convidados, backup), regras de firewall explícitas, DNS filtrado, VPN com MFA, desabilitar protocolos legados.
- Varredura e testes só com autorização escrita: nmap -sV -O host; nmap --script vuln host (informativo); testes de aplicação com OWASP ZAP ou Burp em ambientes autorizados.

## Vulnerabilidades e senhas
- CVE = identificador público de falha; CVSS = gravidade (0-10); priorizar o que é explorado ativamente (catálogo KEV da CISA), exposto à internet e crítico para o negócio.
- Senhas: gerenciador de senhas, frases longas, MFA preferindo app autenticador/FIDO2; hashes: nunca MD5/SHA1 puro para senhas, usar bcrypt/scrypt/Argon2.
- Cripto: TLS 1.2+ (preferir 1.3), certificados com validade monitorada (openssl s_client -connect host:443; openssl x509 -noout -dates).

## Boas práticas de backup contra ransomware
- Regra 3-2-1-1-0: 3 cópias, 2 mídias diferentes, 1 fora do local, 1 offline/imutável, 0 erros na verificação de recuperação. Testar restauração periodicamente. Credenciais do backup separadas do domínio.
