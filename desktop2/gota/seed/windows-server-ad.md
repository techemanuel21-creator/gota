# Windows Server, Active Directory, GPO, DNS, DHCP, IIS, SQL e diagnóstico
Fonte: conhecimento base do Gota

## Active Directory
- Conceitos: **floresta/domínio/OU**, **DC** (controladores), **Catálogo Global**, **FSMO** (Schema Master, Domain Naming, PDC Emulator, RID, Infrastructure), **sites e serviços**, **replicação** (KCC, intersite), **SYSVOL/NETLOGON** (DFSR), **Kerberos/NTLM**, **LDAP/LDAPS**, **GPO**, **trusts**.
- Saúde do AD: `dcdiag /v`, `dcdiag /test:dns`, `repadmin /replsummary`, `repadmin /showrepl`, `repadmin /syncall /AdeP`, `netdom query fsmo`, `nltest /dsgetdc:dominio`, `w32tm /monitor`. Falha de replicação: DNS (registros SRV/_msdcs), horário, firewall (RPC 135 + dinâmicas, 389, 445, 88, 53), conta do computador, tombstone lifetime vencido (lingering objects), USN rollback (restore indevido de VM de DC).
- **Conta bloqueada (evento 4740 no DC PDC emulator)**: `Get-ADUser usuario -Properties LockedOut,BadLogonCount,LastBadPasswordAttempt`, `Search-ADAccount -LockedOut`, `Unlock-ADAccount`. Descubra a **origem** (campo Caller Computer Name do 4740): serviço, tarefa agendada, celular com senha antiga, mapeamento de rede, sessão RDP aberta.
- Senha expirada, política: `Get-ADDefaultDomainPasswordPolicy`, `Get-ADFineGrainedPasswordPolicy`, `net user usuario /domain`.
- **Domínio não confiável/“trust relationship failed”**: senha de máquina fora de sincronia. `Test-ComputerSecureChannel -Repair -Credential (Get-Credential)` ou `Reset-ComputerMachinePassword`, ou reingressar no domínio.
- Recuperação: **Lixeira do AD** (`Get-ADObject -IncludeDeletedObjects -Filter 'isDeleted -eq $true' | Restore-ADObject`), restauração autoritativa (`ntdsutil`), backup do System State (`wbadmin start systemstatebackup`). Nunca restaure DC de snapshot de VM sem suporte (VM-GenerationID ajuda).
- Segurança: veja seguranca-defesa-e-resposta.md.

## Group Policy
- Ordem de aplicação **LSDOU** (Local, Site, Domain, OU); herança, Enforced, Block Inheritance, Security Filtering, WMI filter, loopback. Diagnóstico: `gpupdate /force`, `gpresult /r` (ou `/h rel.html`), `rsop.msc`, Visualizador de Eventos > GroupPolicy/Operational, `Get-GPOReport`. Falhas: DNS, SYSVOL/DFSR, permissão de leitura do grupo "Authenticated Users" (após MS16-072 o computador precisa de leitura), cache de credenciais, latência de logon.

## DNS e DHCP no Windows
- DNS: zonas integradas ao AD, encaminhadores, scavenging, registros dinâmicos; `dnscmd /info`, `Get-DnsServerZone`, `Clear-DnsServerCache`, `ipconfig /registerdns`. Cliente do domínio deve usar **apenas DNS do AD** na placa.
- DHCP: failover (load balance/hot standby), escopos, reservas, autorização no AD; `Get-DhcpServerv4Scope`, `Get-DhcpServerv4Lease -ScopeId`, `Get-DhcpServerv4Statistics`.

## Serviços, desempenho e manutenção
- Serviços: `Get-Service | ? Status -eq Stopped`, `Set-Service -StartupType`, `sc qc/query/failure`, dependências, conta de logon, permissões (evento 7000/7001/7009/7023/7024/7031/7034/7045 no System).
- Desempenho: `Get-Counter '\Processor(_Total)\% Processor Time'`, `\Memory\Available MBytes`, `\PhysicalDisk(_Total)\Avg. Disk sec/Read`; Gerenciador de Tarefas, Monitor de Recursos, `perfmon /rel`, Process Explorer, `typeperf`.
- Espaço: `Get-PSDrive C`, `WinDirStat`/`TreeSize`, limpar `C:\Windows\SoftwareDistribution\Download`, `Dism /online /Cleanup-Image /StartComponentCleanup`, `C:\Windows\Temp`, logs do IIS, `$Recycle.Bin`, VSS (`vssadmin list shadowstorage`), dumps. Veja a skill disco-cheio-windows.
- Atualizações: WSUS/Windows Update, `Get-WindowsUpdateLog`, `DISM /Online /Cleanup-Image /RestoreHealth`, `sfc /scannow`; falhas comuns: serviços wuauserv/bits/cryptsvc, componentes corrompidos, espaço.
- Reparo de boot: WinRE, `bootrec /fixmbr /fixboot /scanos /rebuildbcd`, `bcdboot C:\Windows`, `chkdsk /f`, BitLocker (chave de recuperação), `sfc /scannow /offbootdir=C:\ /offwindir=C:\Windows`.
- Tela azul (BSOD): código (`IRQL_NOT_LESS_OR_EQUAL`, `PAGE_FAULT_IN_NONPAGED_AREA`, `DRIVER_IRQL...`, `KERNEL_DATA_INPAGE_ERROR` = disco, `CRITICAL_PROCESS_DIED`), dump em `C:\Windows\Minidump`, analisar com WinDbg (`!analyze -v`) ou BlueScreenView; atualize/remova drivers recentes, teste RAM (mdsched) e disco.

## Remoto e automação
RDP (3389; NLA; Gateway), **WinRM/PowerShell Remoting** (`Enter-PSSession`, `Invoke-Command`, `Enable-PSRemoting`), SSH nativo, **Task Scheduler** (`schtasks`), **Event Viewer** (`wevtutil`, `Get-WinEvent -FilterHashtable @{LogName='System';Id=41}`), **Windows Admin Center**, **DSC/Ansible/Intune/SCCM(MECM)**.

## IIS, SQL Server e outros
- **IIS**: sites, app pools (identidade, reciclagem), bindings, certificados, logs `C:\inetpub\logs\LogFiles`, erros 401/403/404/500/502/503, `appcmd`, Failed Request Tracing.
- **SQL Server**: instâncias, modelos de recuperação (Simple/Full), backups full/diff/log, jobs do SQL Agent, `sys.dm_exec_requests`, bloqueios (`sp_who2`, `sys.dm_tran_locks`), índices, tempdb, planos de execução, log cheio (backup de log ou mudança de modelo), `DBCC CHECKDB`. Para Veeam: Application-aware com VSS SQL Writer.
- **Exchange/M365**: fila de mensagens, DAG, `Get-MessageTrackingLog`, SPF/DKIM/DMARC, conectores, Defender for Office, MFA e acesso condicional no Entra ID.
- **File Server**: SMB shares, NTFS, ACLs (`icacls`), cotas FSRM, DFS-N/DFS-R, Shadow Copies, `Get-SmbShare`, `Get-SmbSession`, `Get-SmbOpenFile`.
