# Veeam Backup & Replication: mensagens de erro comuns, causas e correções
Fonte: conhecimento base do Gota (confirme detalhes na documentação e nos artigos da Veeam para a versão instalada: helpcenter.veeam.com, veeam.com/kb)

## Como ler uma falha
- Abra **Home > Jobs**, dê dois cliques na sessão. Na lista "Action" leia a **primeira linha com erro (X vermelho)**: ela é a causa; as seguintes costumam ser efeito.
- Estados: Success, Warning (terminou, mas com ressalva), Failed. O job tenta de novo sozinho (Retry, padrão 3 vezes) antes de falhar; o resultado final vale para a última tentativa.
- Logs no servidor de backup: `C:\ProgramData\Veeam\Backup\` (um log por job: `Job.<nome>.log`, tarefas `Task.*.log`), `Svc.VeeamBackup.log` (serviço principal), `Agent.*` (data movers). Para abrir chamado: **Menu > Help > Support Information** (exporta o pacote de logs).
- Serviços principais: Veeam Backup Service, Veeam Broker Service, Veeam Data Mover (nos proxies/repositórios), Veeam Mount Service, Veeam Installer Service, Veeam vPower NFS. Reiniciar serviços com job rodando aborta o job.

## "Job aborted due to server termination" / "Job has been terminated"
O job estava rodando quando o **serviço Veeam Backup ou o próprio servidor foi encerrado/reiniciado**.
Causas mais comuns: reinício por Windows Update ou patch, queda de energia ou desligamento forçado, travamento/reinício do serviço Veeam (antivírus matando o processo, falta de memória, atualização do Veeam), snapshot/migração da VM do servidor de backup, desligamento planejado durante a janela de backup.
Como investigar: Visualizador de Eventos > Sistema: eventos 41 (Kernel-Power), 6008 (desligamento inesperado), 1074 (quem reiniciou), 7036/7034 (serviço parou); Application: erros do Veeam; `Svc.VeeamBackup.log` na hora da falha.
Correção: ajustar a janela de patch para não coincidir com os jobs; exclusões de antivírus para as pastas e processos do Veeam; confirmar que não há reinício agendado; depois use **Retry** ou rode o job de novo. Em jobs de fita, o cartucho pode ficar travado no drive: faça **Rescan** da biblioteca e, se preciso, descarregue a fita (Tape Infrastructure > Libraries > Drives > Eject).

## VSS e snapshot de aplicação
- "Failed to create VSS snapshot", "VSS_E_*", "Failed to freeze guest, wait timeout 900 seconds": no guest `vssadmin list writers` (todos "Stable"). Writer em falha: reiniciar o serviço dele (SQL Writer, NTDS, etc.) ou o servidor. Veja `vssadmin list shadowstorage` e deixe espaço livre no volume (pelo menos 10 a 15 por cento). Eventos VSS e VolSnap no log Application/System.
- Sem VSS (crash-consistent): desative "application-aware processing" só como solução temporária.
- "Cannot connect to guest agent"/"RPC function call failed": falha de rede/DNS/firewall do servidor de backup até o guest (portas 135, 445, 6160 e faixa 49152-65535 dinâmica; para guest interaction proxy veja a documentação), credencial sem direito de administrador local, serviço Remote Registry ou RPC parado, UAC remoto em máquinas fora do domínio.

## VMware
- "Another task is already in progress" / "A general system error occurred": já há tarefa no vCenter/ESXi na VM (consolidação, vMotion, snapshot). Veja Tasks no vSphere Client e aguarde ou cancele.
- "VM disks consolidation is needed": snapshots órfãos. No vSphere: VM > Snapshots > Consolidate. Pode demorar com discos grandes.
- "Unable to allocate processing resources. Error: No backup proxy is available / insufficient resources": proxy desligado, sem slots (task slots em Manage Proxies), ou limite de tarefas no repositório; ajuste "Max concurrent tasks".
- "Failed to connect to vCenter/ESXi", "SSL certificate": credencial, DNS, certificado alterado (aceite/atualize o certificado em Managed Servers), porta 443.
- "CBT" ("Cannot use CBT" / "CBT data is invalid"): rastreamento de blocos alterados quebrado; o Veeam o redefine e lê a VM inteira no próximo ciclo (mais lento uma vez). Evite alterar CBT por script.
- Snapshot muito antigo ou delta grande: consolidar antes; desempenho cai com snapshots longos.
- NBD x HotAdd x Direct SAN: modo de transporte afeta velocidade; HotAdd exige proxy como VM no mesmo cluster/datastore acessível; Direct SAN exige LUNs mapeados e iSCSI/FC visível.

## Hyper-V
- Falha com "Cannot create checkpoint"/"WMI": serviço Hyper-V VMMS, integração (VSS) dentro do guest, espaço no volume do host, nome de VM com caracteres incomuns; em cluster, use o nome do cluster e o "Off-host proxy" corretamente.

## Repositório e armazenamento
- "Insufficient storage space"/"There is not enough space on the disk": sem espaço; veja retenção, GFS, backups órfãos (Disk (Orphaned)) e "Scale-out Backup Repository" (extents em manutenção).
- "Access is denied"/"The network path was not found" para SMB: credencial do repositório, permissão NTFS/compartilhamento, assinatura SMB, DNS, antivírus varrendo o arquivo. Preferir repositório Windows/Linux com agente (data mover) a SMB direto para desempenho.
- "Backup file is corrupted" / falha de **health check**: rode "Health check" ou crie um **Active Full**; verifique disco/controladora/dedup do repositório (SMART, log do array).
- Linux hardened (imutável): backup não pode ser apagado antes do fim da imutabilidade; "Failed to delete/merge" ligado a retenção maior que a imutabilidade; relógio do servidor (NTP) incorreto causa erros de imutabilidade.
- Cadeia com "merge" lento ou falho: espaço temporário, I/O do repositório, antivírus.

## Fita (resumo; veja a nota específica de fita)
"No tapes available in media pool", "Tape is write protected", "Drive requires cleaning", "Failed to open tape device", "Tape library not responding": veja veeam-fita-tape.md.

## Banco de configuração, licença e console
- Console não conecta/"Veeam Backup Service is not running": serviço parado, PostgreSQL/SQL parado ou sem espaço, certificado, porta 9392. Verifique `services.msc` e o log `Svc.VeeamBackup.log`.
- Licença: Home > License; expirada ou sem sockets/instâncias suficientes faz jobs falharem ("license expired/exceeded"). A edição aparece no rodapé do console (ex.: Enterprise Plus).
- Sempre mantenha **backup da configuração do Veeam** (Configuration Backup) em local separado: é o que restaura o servidor de backup.

## Boas práticas de diagnóstico
1. Leia a primeira linha de erro. 2. Veja se só uma VM/objeto falha (problema do objeto) ou todos (infra: repositório, rede, serviço, credencial). 3. Confira o que mudou (patch, reinício, troca de senha, certificado, DNS, firewall). 4. Teste a conectividade do servidor de backup ao alvo (nome, porta). 5. Corrija e use **Retry** apenas nos itens que falharam. 6. Se repetir, abra chamado com o pacote de logs e os horários exatos.
