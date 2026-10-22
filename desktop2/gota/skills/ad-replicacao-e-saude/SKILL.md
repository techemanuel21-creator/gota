---
name: ad-replicacao-e-saude
description: Use para verificar saúde do Active Directory: replicação, DNS, FSMO, SYSVOL e controladores de domínio.
keywords: active directory, ad, replicação, dcdiag, repadmin, fsmo, sysvol, dns, controlador de domínio, kerberos
---
# Active Directory: saúde e replicação

1. Em um DC: `dcdiag /v` e `dcdiag /test:dns`; `repadmin /replsummary` (falhas e deltas), `repadmin /showrepl`, `netdom query fsmo`.
2. Falha de replicação: confira DNS (registros SRV em `_msdcs`, cada DC apontando para DNS do AD), horário (`w32tm /query /status`, tolerância 5 min do Kerberos), portas (53, 88, 135, 389, 445, 636, 3268 e dinâmicas RPC), SYSVOL (DFSR, evento 4012/2213).
3. Erros típicos: 8453 (acesso negado à replicação), 1722 (RPC indisponível), 8606/8456, "lingering objects" (DC ficou desligado além do tombstone lifetime).
4. Corrija a causa (DNS, horário, rede) e force: `repadmin /syncall /AdeP`. Nunca restaure DC de snapshot comum; use backup de System State ou procedimentos suportados.
5. Depois: valide logon, GPO (`gpupdate /force`, `gpresult /r`) e tenha backup de System State recente de pelo menos dois DCs.
