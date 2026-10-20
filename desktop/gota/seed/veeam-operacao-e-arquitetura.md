# Veeam Backup & Replication: arquitetura, jobs, retenção, restauração e PowerShell
Fonte: conhecimento base do Gota (confirme detalhes na documentação da versão em uso: helpcenter.veeam.com)

## Componentes e portas (conferir na documentação da versão)
- **Backup Server** (console, serviços, banco PostgreSQL nas versões atuais), **Proxy** (lê e envia dados), **Repositório** (destino), **Gateway server**, **Mount server**, **WAN accelerator**, **Tape server**, **Guest interaction proxy**, **Cloud connect**.
- Portas típicas: console/serviço 9392 (e 9401 em versões mais antigas para o banco de configuração local), data mover 6162, instalador/componentes 6160, transporte entre componentes na faixa 2500-3300 (alguns usam 2500-5000 conforme versão), vSphere 443, SMB 445, RPC 135 + dinâmicas, SSH 22 para Linux. Sempre confirme na página "Used Ports" da documentação.
- Banco de configuração: faça **Configuration Backup** diário para fora do servidor; ele restaura o ambiente inteiro do Veeam.

## Tipos de job e modos de backup
- **Backup** de VMs (VMware, Hyper-V, Nutanix AHV via plugin), **Agent** (Windows/Linux físicos), **File/NAS backup**, **File to Tape**, **Backup to Tape**, **Backup Copy** (cópia para outro repositório), **Replication** (réplica pronta para ligar), **SureBackup** (verifica se o backup liga).
- Métodos: **incremental com full sintético** (full gerado a partir dos incrementais, semanal), **incremental forward com active full** periódico, **reverse incremental** (o full fica sempre atualizado; mais I/O). **GFS** guarda pontos semanais/mensais/anuais além da retenção curta.
- **Retenção**: número de pontos de restauração (ou dias). Backups órfãos (de jobs removidos) ocupam espaço e aparecem em "Disk (Orphaned)".
- **Regra 3-2-1-1-0**: 3 cópias, 2 mídias diferentes, 1 fora do local, 1 offline/imutável, 0 erros em testes de restauração (SureBackup).

## Imutabilidade e segurança
- **Linux Hardened Repository** (flag imutável por tempo), **S3 Object Lock**, fita offline. Credenciais do repositório e do vCenter diferentes das do domínio; MFA no console; servidor de backup fora do domínio ou com acesso restrito; patches em dia; desabilitar RDP aberto; segmentar a rede de backup.
- Proteja o **Configuration Backup** com senha (criptografia) e guarde a senha: sem ela não restaura credenciais.

## Restauração
- **Instant Recovery** (liga a VM direto do backup via vPower NFS), **Entire VM restore**, **Restore guest files** (Windows/Linux), **Application items** (AD, Exchange, SQL, SharePoint, Oracle com Explorers), **Disk restore**, **Export disk**, **Restore to Azure/AWS**.
- Sempre teste a restauração em ambiente isolado. Antes de restaurar de um incidente (ransomware), use **Secure Restore** para varrer com antivírus.
- Sequência segura de recuperação: isolar a origem do problema, escolher ponto de restauração anterior à infecção, restaurar para rede isolada, validar, só então reconectar.

## Rotina operacional
- Diariamente: revisar sessões com Warning/Failed, espaço dos repositórios, jobs que não rodaram, alertas por e-mail (configure SMTP) e Veeam ONE se houver.
- Semanalmente: conferir licenças, tamanho da cadeia, tempo de merge, saúde dos repositórios (SMART/array), versão e patches.
- Mensalmente: teste de restauração, SureBackup, revisão de retenção, atualização do Veeam (leia o release notes), teste de recuperação do servidor de backup a partir do Configuration Backup.

## PowerShell (módulo/snap-in do Veeam instalado com o console)
```powershell
Get-VBRJob | Select Name, JobType, IsRunning, @{n='Ultimo';e={$_.GetLastResult()}}      # jobs e último resultado
Get-VBRBackupSession | Sort CreationTime -Desc | Select -First 20 JobName, Result, CreationTime, EndTime
Get-VBRJob -Name "NOME" | Start-VBRJob            # roda um job
Get-VBRRestorePoint -Backup (Get-VBRBackup -Name "NOME") | Sort CreationTime -Desc | Select -First 5
Get-VBRBackupRepository | Select Name, Type, Path, @{n='LivreGB';e={[math]::Round($_.GetContainer().CachedFreeSpace.InGigabytes,1)}}
Get-VBRTapeJob; Get-VBRTapeLibrary; Get-VBRTapeMediaPool        # fita
```
(O nome exato de alguns cmdlets e propriedades muda entre versões: use `Get-Command *VBR*` e `Get-Help`.)

## Dimensionamento rápido
- Proxy: ~1 vCPU e 2 GB de RAM por tarefa simultânea. Repositório: dimensionar pelo I/O do merge, não só pela capacidade. Rede dedicada ou segmentada para backup. Evite colocar o repositório no mesmo storage/array dos dados de produção.
- Janela de backup = dados alterados por dia ÷ velocidade efetiva; leve em conta o tempo do merge/full sintético e da cópia (Backup Copy) para fora.
