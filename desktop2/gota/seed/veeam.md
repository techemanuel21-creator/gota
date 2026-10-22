# Veeam Backup & Replication: conceitos, arquitetura e solução de problemas
Fonte: conhecimento base do Gota (confirme detalhes na documentação da versão instalada em helpcenter.veeam.com)

## Arquitetura
- Backup Server: coordena tudo (console, jobs, banco de configuração PostgreSQL nas versões atuais ou SQL Server em versões antigas).
- Proxy: processa os dados (lê VMs/dados, compacta, deduplica e envia). Repositório: onde ficam os backups (disco local, SMB, NFS, Linux hardened, deduplicadoras, nuvem/objeto). Gateway server: ponte para SMB/objeto. Mount server: restaura arquivos/itens. WAN accelerator: acelera cópias remotas.
- Transporte do proxy VMware: Direct Storage Access (mais rápido, SAN), Virtual Appliance (hotadd), Network (NBD, mais lento).
- Portas usuais (verificar na versão): 443 para vCenter/ESXi; 6160 (serviço instalador/Veeam Installer); 6162 (Data Mover); 2500-3300 (faixa de transferência de dados entre componentes); 9392 (serviço do Backup Server); 9419 (API REST); 10006 (mount server); 135, 445 e portas dinâmicas RPC para componentes Windows.

## Tipos de jobs e recursos
- Backup job (VM, agente Windows/Linux, arquivos NAS), Backup copy job (cópia para outro local; regra 3-2-1), Replication job (réplica de VM em DR), CDP, SureBackup (verifica se o backup realmente sobe e funciona: o "0 erros" do 3-2-1-1-0), Scale-Out Backup Repository (SOBR com performance tier, capacity tier e archive tier), Veeam ONE (monitoramento e relatórios), Instant Recovery (liga a VM direto do backup), restauração de arquivo, item (Exchange/SharePoint/AD/SQL/Oracle) e de volume inteiro.
- Imutabilidade: Linux hardened repository ou objeto com object lock. Secure restore e Inline malware detection ajudam contra ransomware.

## Problemas e verificações comuns
- Job falha com "Unable to allocate processing resources": faltam slots de tarefa no proxy/repositório (aumentar limite de tarefas concorrentes ou ajustar janela).
- "Cannot connect to guest / Guest processing failed": credenciais da VM, VMware Tools, firewall (RPC, administrative shares, ADMIN$), UAC; testar com a opção de guest processing e credenciais corretas. VSS: vssadmin list writers e vssadmin list providers; writer com erro costuma exigir reiniciar o serviço relacionado.
- Snapshot que não consolida / VM "consolidation needed": consolidar pelo vSphere; checar snapshots órfãos, espaço no datastore e limites de snapshot.
- Lentidão: ver o gargalo mostrado no job (Source, Proxy, Network, Target). Source alto = leitura do datastore; Target alto = repositório; Network = banda/latência. Mudar o modo de transporte, adicionar proxy, ajustar compressão/deduplicação.
- "Repository is out of free space": aumentar retenção menor, mover backups, adicionar extent ao SOBR, remover backups antigos pelo console (Backups > Disk > Remove from disk) e nunca apagar arquivos .vbk/.vib manualmente fora do Veeam.
- CBT (changed block tracking) com erro: reset de CBT via Veeam ou desligar/ligar a VM; aumenta o tamanho do próximo incremental.
- Certificados/TLS e serviços: serviços Veeam (Get-Service Veeam*) devem estar em execução; logs em C:\ProgramData\Veeam\Backup (Svc.VeeamBackup.log e logs por job); exportar logs: botão direito no job ou menu principal > Export Logs.
- PowerShell: Add-PSSnapin VeeamPSSnapin (versões antigas) ou módulo Veeam.Backup.PowerShell; comandos como Get-VBRJob, Get-VBRBackupSession, Start-VBRJob, Get-VBRBackupRepository, Get-VBRRestorePoint.

## Boas práticas
- Servidor de backup fora do domínio de produção ou com proteção reforçada, MFA no console, repositório imutável, criptografia dos backups com senha guardada fora, proxy e repositório separados em ambientes grandes, backup do próprio banco de configuração (Configuration Backup) em local diferente, SureBackup agendado, relatórios e alertas por e-mail, manter a versão atualizada com os patches de segurança.
