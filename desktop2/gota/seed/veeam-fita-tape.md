# Veeam e fita (tape): bibliotecas, drives, media pools, jobs File to Tape e Backup to Tape
Fonte: conhecimento base do Gota (confirme detalhes na documentação da Veeam e do fabricante da biblioteca)

## Conceitos
- **Tape Infrastructure**: servidor de fita (tape server, o Windows ao qual a biblioteca está ligada por SAS/FC), **bibliotecas** (library/changer com slots, drives e mailslot), **drives** LTO e **cartuchos**.
- **Media pools**: grupos de fitas. Tipos: **Custom** (a fita é usada até acabar), **GFS** (rotação semanal, mensal, trimestral, anual), **Media set** (conjuntos). Há o pool **Free** (fitas livres), **Unrecognized** (sem rótulo do Veeam), **Imported** (de outro servidor), **Retired** (aposentadas) e **Offline**.
- Tipos de job: **File to Tape** (arquivos de um servidor/NAS para fita, ex.: JOB_BACKUP_TAPE_*) e **Backup to Tape** (copia arquivos de backup do Veeam para fita; usado para cópia mensal/GFS). **NDMP** para NAS que suporta.
- Retenção: a fita só pode ser sobrescrita após o fim da retenção do media pool; "Protect data from being overwritten for N days".
- Geração LTO (capacidade nativa aproximada): LTO-5 1,5 TB, LTO-6 2,5 TB, LTO-7 6 TB, LTO-8 12 TB, LTO-9 18 TB; desempenho nativo aproximado: LTO-7 300 MB/s, LTO-8 360 MB/s, LTO-9 400 MB/s. Cada drive lê a própria geração e a anterior (LTO-8 lê LTO-7 e LTO-8; grava LTO-8 e LTO-7).
- Um drive precisa receber dados **continuamente**: se a origem for mais lenta que a velocidade mínima do drive, ele para e volta ("shoe-shining"), o que desgasta e deixa lento. Use origem rápida, vários streams e proxies/storage local de preparo.

## Mensagens e o que fazer
- **"Job aborted due to server termination" / "Job has been terminated"**: o serviço ou o servidor do Veeam foi reiniciado durante o job (patch, queda, serviço travado). Veja a nota de erros comuns. Depois: Rescan da biblioteca, confirmar que o cartucho não ficou no drive, Retry.
- **"No tapes available in media pool" / "There are no available tapes"**: o pool não tem fita livre. Adicione fitas ao pool Free, aposente/recicle fitas com retenção vencida (Tape > Media Pools > Erase), confirme o código de barras/rótulo, ou ajuste a política (permitir pool de overflow).
- **"Tape is write protected"**: fita com a trava de proteção mecânica ou WORM; mude a trava ou use outra.
- **"Failed to open tape device" / "Drive is not ready" / "Tape drive is busy"**: drive em uso por outro processo, driver, cabo SAS/FC, bloqueio por outro host. Verifique o status em Tape Infrastructure, reinicie o **Veeam Tape service** se aplicável, reveja os drivers (use o driver do **fabricante** da biblioteca/drive, não o genérico do Windows para o changer), reinicie a biblioteca e o servidor de fita se necessário.
- **"Drive requires cleaning"**: carregue fita de limpeza (cleaning cartridge) ou rode a limpeza na biblioteca; fitas muito usadas ou sujas causam erros de leitura/escrita.
- **Fita "Unrecognized"/"Foreign"**: fita com formato desconhecido; **Catalog** ou **Import** conforme o caso; apagar (Erase) só se tiver certeza.
- **Erros de hardware ("hardware error", "medium error", CRC)**: reveja logs do drive/biblioteca (interface web/SNMP), troque a fita suspeita, limpe o drive, atualize firmware.
- **"Source file is locked/Access denied"** em File to Tape: arquivo aberto, permissão da conta do job, snapshot VSS não usado; prefira ler de um snapshot/compartilhamento estável e use conta com direito de leitura.
- **"Library not found/changer offline"**: cabo, zoneamento FC, driver do changer, modo da biblioteca (sequencial x random); rode **Rescan** e **Inventory**.
- **Job lento**: origem lenta (arquivos pequenos), drive abaixo da velocidade mínima, SAS/FC compartilhado, antivírus escaneando os arquivos lidos, banda do NAS.

## Operação segura de fita
- Mantenha cópia **fora do local** (offsite) e **offline** (air gap): fita removida é imune a ransomware.
- Registre onde cada fita está (barcode, pool, data de fim de retenção). Teste a **restauração** periodicamente.
- Conferir: `Get-VBRTapeLibrary`, `Get-VBRTapeMediaPool`, `Get-VBRTapeJob` (módulo PowerShell do Veeam) para inventário e estado.
- Em falhas recorrentes: separar se é a **origem** (arquivos/NAS), a **rota** (rede/FC/SAS) ou o **drive/fita**: rode um job pequeno com outra fita e outra origem.
