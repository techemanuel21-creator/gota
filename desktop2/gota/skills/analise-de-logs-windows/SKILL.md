---
name: analise-de-logs-windows
description: Use para investigar eventos do Windows: logons, falhas de login, reinícios, instalações, erros de aplicação ou de sistema.
keywords: log, evento, event viewer, get-winevent, 4624, 4625, 4688, 41, 1074, 6008, 7045, segurança, auditoria
---
# Investigar eventos do Windows

1. Últimos erros do sistema:

```powershell
Get-WinEvent -FilterHashtable @{LogName='System'; Level=2; StartTime=(Get-Date).AddDays(-1)} -MaxEvents 20 | Format-Table TimeCreated,Id,ProviderName,Message -Wrap
```

2. Reinícios: **1074** (desligamento planejado, mostra quem pediu), **6008** (desligamento inesperado) e **41** (Kernel-Power: queda de energia ou travamento).
3. Logins: **4624** (sucesso) e **4625** (falha). O tipo de logon diz a origem (2 local, 3 rede, 10 RDP):

```powershell
Get-WinEvent -FilterHashtable @{LogName='Security'; Id=4625; StartTime=(Get-Date).AddHours(-6)} -MaxEvents 30 | Select-Object TimeCreated,@{n='Usuario';e={$_.Properties[5].Value}},@{n='Origem';e={$_.Properties[19].Value}}
```

4. Persistência suspeita: **7045** (serviço novo), **4698** (tarefa agendada nova) e **4688** (processo novo, se a auditoria estiver ligada).
5. Filtre sempre por período e por ID; sem isso a consulta fica lenta. Para guardar o resultado: `| Export-Csv eventos.csv -NoTypeInformation`.
