---
name: teste-de-restauracao
description: Use ao planejar ou executar um teste de restauração de backup para provar que a recuperação funciona.
keywords: restauração, teste, backup, dr, rto, rpo, surebackup, instant recovery, validação
---
# Teste de restauração de backup

1. Defina o escopo: uma VM crítica, um arquivo, um item de aplicação (e-mail, tabela, objeto AD) e o ponto de restauração desejado.
2. Restaure em **rede isolada** (nunca por cima da produção): no Veeam use Instant Recovery ou Entire VM restore para outro host/datastore e rede de teste, ou SureBackup automático.
3. Valide: a VM liga, serviços sobem, aplicação responde, dados corretos, login funciona. Para bancos, rode verificação de integridade.
4. Meça o **tempo** (compare com o RTO) e a perda de dados (compare com o RPO). Registre.
5. Limpe o ambiente de teste (parar Instant Recovery, apagar a cópia) e documente falhas e correções.
6. Repita com periodicidade definida (mensal ou trimestral) e após mudanças grandes. Garanta que ao menos uma cópia seja imutável/offline.
