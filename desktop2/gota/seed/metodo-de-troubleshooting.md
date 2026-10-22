# Método de troubleshooting em TI (como um especialista pensa)
Fonte: conhecimento base do Gota

## Passos
1. **Definir o sintoma exato**: o que falha, mensagem completa, quando começou, quem é afetado (um, vários, todos), é intermitente ou constante, o que mudou antes.
2. **Delimitar o escopo**: um objeto ou todos? uma localidade ou várias? Compare com um caso que funciona.
3. **Levantar hipóteses** do mais provável e barato ao mais raro. Mudanças recentes (patch, senha, certificado, DNS, firewall, firmware, espaço em disco) explicam a maioria.
4. **Evidências antes de agir**: logs, eventos, métricas, a primeira linha de erro (não a última). Hora exata do erro para correlacionar.
5. **Testar uma hipótese por vez** e mudar uma coisa por vez; anotar o que foi feito para poder reverter.
6. **Corrigir a causa raiz**, não só o sintoma (reiniciar resolve o sintoma; descubra por que travou).
7. **Validar** (o usuário/serviço realmente voltou?) e **documentar** (causa, correção, prevenção).

## Perguntas rápidas que resolvem muito
- Hora/data e fuso estão certos? (certificados, Kerberos, backup)
- Há espaço em disco e memória? Inodes?
- O nome resolve (DNS) e a porta responde? Firewall no meio?
- A credencial expirou, foi trocada ou a conta bloqueou?
- O serviço está rodando e o disco/volume está montado?
- Houve reinício, patch ou queda de energia?
- Antivírus ou EDR está bloqueando o processo/arquivo?
- Funciona de outra máquina ou com outra conta? (isola cliente x servidor x conta)

## Interpretando mensagens
- "Access denied" = permissão/credencial; "not found / cannot resolve" = nome/DNS/caminho; "timed out" = rede/firewall/serviço lento; "connection refused" = nada escutando na porta (serviço parado); "certificate" = data, cadeia, nome (SAN) ou expiração; "No space left" = disco ou inode; "RPC unavailable" = rede/portas/serviço RPC; "locked/in use" = outro processo (lsof, handle.exe, Resource Monitor).
- Em Windows, o log correto: System (serviços, disco, driver), Application (aplicações), Security (logon, auditoria), e logs específicos do produto. Em Linux: `journalctl`, `/var/log`, `dmesg`.

## Comunicação com o usuário
Explique o que encontrou em linguagem simples, diga o impacto, o plano e o prazo; pergunte antes de qualquer ação destrutiva (apagar, reiniciar produção, restaurar por cima); confirme que há backup. Em incidentes de segurança, preserve evidências antes de limpar.

## Segurança operacional
Faça mudança em horário adequado, com plano de reversão e janela aprovada; teste em homologação quando existir; nunca execute scripts desconhecidos como administrador; não desative antivírus/firewall "para testar" sem alternativa controlada; registre quem fez o quê.
