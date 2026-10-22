# Windows: comandos e administração (CMD e PowerShell)
Fonte: conhecimento base do Gota

## Diagnóstico do sistema
- systeminfo: versão do Windows, RAM, uptime, hotfixes. hostname, whoami /all (usuário, grupos, privilégios).
- Get-ComputerInfo (PowerShell); Get-CimInstance Win32_OperatingSystem | select LastBootUpTime.
- tasklist / Get-Process: processos. Get-Process | sort CPU -desc | select -first 10. taskkill /PID 1234 /F ou Stop-Process -Id 1234 -Force.
- Serviços: Get-Service; sc query; Restart-Service NomeDoServico; Set-Service -Name X -StartupType Disabled; sc config X start= demand.
- Disco: Get-PSDrive -PSProvider FileSystem; Get-Volume; chkdsk C: /scan (somente leitura online); wmic diskdrive get status.
- Integridade do sistema: sfc /scannow, depois DISM /Online /Cleanup-Image /RestoreHealth, reiniciar e repetir sfc.
- Atualizações: Get-HotFix; usoclient StartScan; wuauclt /detectnow (antigo). Reset do Windows Update: parar wuauserv e bits, renomear C:\Windows\SoftwareDistribution, iniciar de novo.
- Eventos: Get-WinEvent -LogName System -MaxEvents 50; Get-WinEvent -FilterHashtable @{LogName='Security';Id=4625} (falhas de logon); eventvwr.msc.
- Eventos úteis: 4624 logon com sucesso, 4625 falha de logon, 4672 privilégios especiais, 4688 processo criado, 4720 conta de usuário criada, 4728/4732 usuário adicionado a grupo, 1102 log de auditoria limpo, 7045 serviço instalado, 41 Kernel-Power (desligamento inesperado), 6008 desligamento inesperado.
- Telas azuis: dumps em C:\Windows\Minidump; analisar com WinDbg (!analyze -v); códigos comuns: 0x0000007E, 0x0000003B, DPC_WATCHDOG_VIOLATION, IRQL_NOT_LESS_OR_EQUAL (driver).

## Rede
- ipconfig /all, ipconfig /flushdns, ipconfig /release e /renew; Get-NetIPConfiguration; Get-NetAdapter.
- ping, tracert, pathping, nslookup nome, Resolve-DnsName nome, Test-NetConnection host -Port 443.
- netstat -ano (conexões e PID); Get-NetTCPConnection -State Listen; netsh advfirewall show allprofiles.
- Reset de rede: netsh winsock reset; netsh int ip reset; reiniciar.
- Compartilhamentos: net use; net share; Get-SmbShare; Get-SmbConnection.

## Usuários e grupos
- net user; net user nome /add; net localgroup administrators; Get-LocalUser; Add-LocalGroupMember -Group Administradores -Member nome.
- Domínio: gpupdate /force; gpresult /r; whoami /groups; nltest /dsgetdc:dominio; Get-ADUser (módulo ActiveDirectory).

## Arquivos e automação
- robocopy origem destino /MIR /R:2 /W:5 /LOG:log.txt (espelha; cuidado: /MIR apaga no destino o que não existe na origem).
- icacls pasta (permissões); takeown /f arquivo; attrib.
- schtasks /create /tn Nome /tr "script" /sc daily /st 02:00; schtasks /query; Task Scheduler = taskschd.msc.
- Variáveis de ambiente: setx NOME valor (permanente); $env:NOME no PowerShell.
- Winget: winget search/install/upgrade --all.
- Registro: reg query HKLM\Software\...; reg export; Get-ItemProperty; sempre exportar antes de alterar.

## PowerShell essencial
- Get-Help comando -Examples; Get-Command *termo*; Get-Member; | Where-Object, | Select-Object, | Sort-Object, | Export-Csv.
- Execução de scripts: Get-ExecutionPolicy; Set-ExecutionPolicy RemoteSigned -Scope CurrentUser.
- Remoto: Enter-PSSession, Invoke-Command -ComputerName X -ScriptBlock {...}; requer WinRM (Enable-PSRemoting).
