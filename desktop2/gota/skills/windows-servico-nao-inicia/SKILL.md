---
name: windows-servico-nao-inicia
description: Use quando um serviço do Windows não inicia, trava em "Iniciando" ou para sozinho.
keywords: windows, serviço, service, não inicia, erro 1053, erro 1068, dependência, sc, get-service, event viewer, parou
---
# Serviço do Windows que não sobe

1. Veja o estado e a configuração:

```powershell
Get-Service NomeDoServico | Format-List Name,Status,StartType
sc.exe qc NomeDoServico
```

2. Leia o log de eventos no horário da falha:

```powershell
Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Service Control Manager'; StartTime=(Get-Date).AddHours(-2)} -MaxEvents 10 | Select-Object TimeCreated,Id,Message
```

   IDs comuns: **7000** e **7009** (não iniciou ou estourou o tempo), **7001** (uma dependência falhou), **7031** e **7034** (parou sozinho), **7045** (serviço novo instalado: confira se foi você).
3. Dependências: `Get-Service NomeDoServico -RequiredServices` e `-DependentServices`. Inicie primeiro o que estiver parado.
4. Causas mais comuns: conta de logon errada ou senha expirada (aba **Log On** em services.msc), porta em uso (`netstat -ano | findstr :PORTA`), pasta ou arquivo sem permissão, .NET ou VC++ faltando.
5. Teste com `Start-Service NomeDoServico`. Se travar, ache o processo com `Get-Process` e finalize com `Stop-Process -Force`, depois tente de novo.
6. Se o aplicativo tiver log próprio, leia as últimas linhas: `Get-Content caminho\app.log -Tail 50`.
