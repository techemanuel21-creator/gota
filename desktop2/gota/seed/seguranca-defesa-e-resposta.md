# Segurança da informação: defesa, hardening, resposta a incidentes, AD, vulnerabilidades
Fonte: conhecimento base do Gota (uso defensivo e educacional)

## Princípios e frameworks
- **CIA** (confidencialidade, integridade, disponibilidade), menor privilégio, defesa em profundidade, zero trust (nunca confie, sempre verifique), segregação de funções, fail-secure.
- Frameworks: **NIST CSF** (Identify, Protect, Detect, Respond, Recover, Govern), **ISO 27001/27002**, **CIS Controls** e **CIS Benchmarks** (hardening), **MITRE ATT&CK** (táticas e técnicas dos atacantes), **OWASP Top 10**, **LGPD** (Brasil: dados pessoais, base legal, DPO, comunicar incidente à ANPD), PCI-DSS.

## Higiene essencial (maior retorno)
1. Patches (SO, firmware, hypervisor, aplicações expostas) com prioridade para falhas exploradas (veja catálogo CISA KEV).
2. **MFA** em e-mail, VPN, admin, console de backup, nuvem. 3. Senhas únicas + gerenciador; LAPS para admin local. 4. Backups imutáveis e testados. 5. EDR/antivírus gerenciado. 6. Inventário de ativos. 7. Segmentação e firewall com regra mínima. 8. Logs centralizados e alertas. 9. Remover RDP/SMB/SSH expostos à internet; usar VPN/ZTNA. 10. Treinamento anti-phishing.

## Active Directory: ataques comuns e defesas
- **Kerberoasting** (contas de serviço com SPN e senha fraca): senhas longas (25+), gMSA, AES. **AS-REP roasting** (sem pré-autenticação): não desativar pré-auth. **Pass-the-Hash/Ticket**, **DCSync** (direitos de replicação), **Golden/Silver Ticket**, **NTLM relay** (exigir SMB signing e LDAP signing/channel binding, desativar NTLM onde possível), **Zerologon/PrintNightmare** (patch), **ADCS ESC1-ESC8** (revisar templates), **GPP cpassword**. 
- Defesas: modelo de camadas (tier 0/1/2), estações de administração privilegiadas (PAW), grupo **Protected Users**, **LAPS**, remover Domain Admin de uso diário, auditoria avançada, monitorar eventos 4624/4625 (logon), 4672 (privilégios), 4720/4728/4732 (contas/grupos), 4768/4769 (Kerberos), 4740 (bloqueio), 1102 (log limpo), 7045 (serviço instalado).
- Ferramentas defensivas: BloodHound (visibilidade de caminhos), PingCastle, Purple Knight, Defender for Identity.

## Resposta a incidentes (NIST SP 800-61)
1. **Preparação** (plano, contatos, ferramentas, backups). 2. **Detecção e análise** (o que, quando, escopo, IOCs, linha do tempo). 3. **Contenção** (isolar hosts/segmentos, desabilitar contas, bloquear IOCs; preferir isolar a desligar para preservar memória quando possível). 4. **Erradicação** (remover persistência, corrigir a causa). 5. **Recuperação** (restaurar de backup limpo, monitorar). 6. **Lições aprendidas**.
- **Ransomware**: isole imediatamente a rede afetada (cabo/switch/VLAN), não pague sem consultar especialistas/jurídico, identifique a variante, preserve evidências (cópia de logs/memória), verifique backups (estão íntegros e fora do alcance?), troque credenciais (krbtgt duas vezes, contas privilegiadas), reconstrua em vez de limpar quando possível, restaure em rede isolada, descubra o vetor inicial (phishing, RDP, VPN sem patch).
- **Conta comprometida**: redefinir senha, revogar sessões/tokens (Entra: Revoke sessions), remover regras de e-mail maliciosas, revisar MFA registrado, logs de acesso, aplicativos OAuth autorizados.
- **Cadeia de custódia**: registre quem coletou o quê, quando, hash dos arquivos (`Get-FileHash`, `sha256sum`).

## Análise de logs e detecção
- Windows: Security/System/Application, Sysmon (processo, rede, DLL), PowerShell ScriptBlock (4104), Defender. Linux: `/var/log/auth.log` ou `secure`, `journalctl`, `auditd`, `last`, `lastb`.
- SIEM/EDR: Wazuh, Elastic, Splunk, Sentinel, Defender XDR. Regras Sigma e YARA. Detecte: logons fora do horário, múltiplas falhas seguidas de sucesso, criação de serviço, execução de `powershell -enc`, `vssadmin delete shadows`, `bcdedit /set recoveryenabled no`, desativação de antivírus, mimikatz/lsass dump, movimentação lateral (PsExec, WMI, WinRM), exfiltração incomum.

## Vulnerabilidades e web
- **CVE/CVSS/EPSS**, priorização por exposição e exploração real. Scanners (Nessus, OpenVAS, Qualys), SAST/DAST/SCA, gestão de dependências.
- **OWASP Top 10**: controle de acesso quebrado, falhas criptográficas, injeção (SQL, comando, LDAP, XSS), design inseguro, configuração incorreta, componentes vulneráveis, falhas de autenticação, integridade de software/dados, falhas de log e monitoramento, SSRF. Defesa: validação, consultas parametrizadas, escape de saída, CSP, cabeçalhos de segurança, segredos fora do código, princípio do menor privilégio.

## Criptografia e PKI
Simétrica (AES-256-GCM), assimétrica (RSA 2048+/ECC), hash (SHA-256; senhas com bcrypt/scrypt/argon2, nunca MD5/SHA1), TLS 1.2/1.3, certificados X.509 (CN/SAN, cadeia, expiração, revogação CRL/OCSP), HSTS. Verifique: `openssl x509 -in cert.pem -noout -text -dates`, `openssl s_client -connect host:443 -servername host`. Chaves privadas nunca em repositório; rotação de segredos; cofre (Vault, Key Vault).

## Linux e Windows hardening (resumo)
Windows: BitLocker, Credential Guard, ASR rules, AppLocker/WDAC, SMB signing, desativar SMBv1/LLMNR/NetBIOS, UAC, auditoria, CIS Benchmark. Linux: SSH por chave + sem root, fail2ban, firewall, SELinux/AppArmor, sudo mínimo, atualizações automáticas de segurança, auditd, `chmod/chown` corretos, remover serviços não usados.
