---
name: veeam-job-abortado-servidor-encerrado
description: Use quando um job do Veeam falhar com "Job aborted due to server termination" ou "Job has been terminated".
keywords: veeam, job, aborted, server termination, terminated, abortado, reinício, serviço, fita, tape
---
# Veeam: "Job aborted due to server termination"

Significa que o **serviço Veeam Backup ou o servidor de backup foi encerrado/reiniciado** enquanto o job rodava. Não é erro do job em si.

1. Veja no Visualizador de Eventos do servidor de backup, na hora da falha: Sistema com IDs **41** (Kernel-Power), **6008** (desligamento inesperado), **1074** (quem reiniciou), **7034/7036** (serviço parou). Se houve reinício, descubra o motivo: Windows Update, queda de energia, manutenção, snapshot ou migração da VM do servidor.
2. Se não houve reinício, só o serviço: abra `C:\ProgramData\Veeam\Backup\Svc.VeeamBackup.log` na hora do erro; procure falta de memória, antivírus encerrando processos, atualização do Veeam ou travamento do banco.
3. Corrija a causa: tire a janela de patch/reinício do horário dos jobs, crie exclusões no antivírus para as pastas e processos do Veeam, garanta energia/UPS, reserve memória para o servidor.
4. Se o job era de **fita**: faça **Rescan** da biblioteca; se a fita ficou no drive, ejete (Tape Infrastructure > Libraries > Drives > Eject) e confirme que a mídia voltou ao slot.
5. Rode o job novamente (botão direito > **Retry** ou **Start**) e confirme Success. Se repetir sem reinício aparente, abra chamado com o pacote de logs (Menu > Help > Support Information).
