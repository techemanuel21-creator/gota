---
name: veeam-fita-falhou
description: Use quando um job de fita do Veeam (File to Tape ou Backup to Tape) falhar ou ficar lento.
keywords: veeam, fita, tape, lto, biblioteca, drive, media pool, file to tape, backup to tape, falha, limpeza
---
# Veeam: job de fita falhou ou está lento

1. Abra a sessão e leia a **primeira linha vermelha**. Se for "aborted due to server termination", veja a skill veeam-job-abortado-servidor-encerrado.
2. Em **Tape Infrastructure**: a biblioteca e os drives estão online? Se não, cabo SAS/FC, driver do fabricante do changer, reinicie o serviço de fita e faça **Rescan/Inventory**.
3. Mensagens frequentes:
   - **Sem fitas disponíveis**: o media pool não tem fita livre; adicione fitas ao pool Free ou recicle fitas com retenção vencida (Erase) e confira rótulos/barcodes.
   - **Write protected**: trave mecânica da fita ou mídia WORM; troque a fita.
   - **Drive requires cleaning**: use a fita de limpeza.
   - **Failed to open device / drive busy**: outro processo usando o drive, driver ou cabo; reinicie serviço/servidor de fita.
   - **Erro de mídia/hardware**: troque a fita suspeita, limpe o drive, veja logs da biblioteca e atualize o firmware.
   - **Arquivo bloqueado/acesso negado na origem**: permissão da conta do job; prefira leitura de snapshot ou compartilhamento estável.
4. Lentidão: a origem precisa alimentar o drive continuamente (acima da velocidade mínima do LTO); arquivos pequenos e NAS lento causam vai-e-volta do drive. Use vários streams, origem rápida e exclusão de antivírus.
5. Confirme depois com um job pequeno em outra fita. Mantenha cópia offline e teste a restauração periodicamente.
