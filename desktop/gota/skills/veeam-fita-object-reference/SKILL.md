---
name: veeam-fita-object-reference
description: Use quando um job de fita (Backup to Tape) do Veeam mostrar "Object reference not set to an instance of an object" ou "Failed to backup some full backup files, skipping the corresponding incremental backups".
keywords: veeam, fita, tape, backup to tape, object reference not set, instance of an object, failed to backup some full backup files, skipping incremental, vbk, finished with errors, job falhou
---
# Veeam: "Object reference not set..." e "Failed to backup some full backup files" em job de fita

**O que significa:** "Object reference not set to an instance of an object" é um erro interno (.NET, referência nula) do serviço do Veeam ao processar um arquivo de backup de origem do job de fita (o `.vbk` citado na linha anterior). O Veeam esperava um objeto (o backup/arquivo no repositório ou no banco de configuração) e ele não estava disponível ou estava inconsistente. "Failed to backup some full backup files, skipping the corresponding incremental backups" é **consequência**: sem o full, os incrementais que dependem dele são pulados. "Processing finished with errors" é só o resumo do job.

**Causas mais comuns:**
1. O arquivo `.vbk` não existe mais ou não abre: a retenção/merge do job de origem apagou ou moveu o arquivo enquanto o job de fita o lia (horários sobrepostos).
2. Repositório offline, indisponível ou com o índice desatualizado (rescan pendente).
3. Cadeia de backup corrompida ou backup removido do banco de configuração.
4. Bug da versão: confira o build e os patches cumulativos instalados.

**Como corrigir, em ordem:**
1. Anote o arquivo citado e o job de origem (ex.: `JOB_BKP_DAILY_...`). Em **Home > Backups > Disk**, veja se o ponto de restauração existe e está íntegro.
2. **Backup Infrastructure > Backup Repositories**: botão direito no repositório > **Rescan**, e confirme que o arquivo existe no disco do repositório.
3. Separe os horários: o job de fita não pode rodar junto com o job de origem (que faz merge e retenção).
4. No job de origem, rode **Health Check** ou um **Active Full** para ter um full novo e íntegro.
5. No job de fita: **Edit**, retire e adicione de novo o backup/job de origem e rode manualmente com **Full backup**.
6. Aplique o patch cumulativo da sua versão se estiver desatualizada.
7. Se continuar, leia `C:\ProgramData\Veeam\Backup\<nome do job>\Job.*.log` e `Svc.VeeamBackup.log` na hora do erro e abra chamado com o pacote de logs (**Menu > Help > Support Information**).