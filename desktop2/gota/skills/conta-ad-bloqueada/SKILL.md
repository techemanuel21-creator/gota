---
name: conta-ad-bloqueada
description: Use quando uma conta do Active Directory fica bloqueada (lockout) repetidamente ou o usuário não consegue entrar.
keywords: active directory, ad, conta, bloqueada, lockout, 4740, 4625, senha, desbloquear, unlock, usuario
---
# Conta do AD bloqueada

1. Confirme o estado:

```powershell
Get-ADUser usuario -Properties LockedOut,BadLogonCount,LastBadPasswordAttempt,PasswordExpired,Enabled | Format-List
```

2. Desbloqueie quando for legítimo: `Unlock-ADAccount -Identity usuario`.
3. Descubra de onde vem o bloqueio. O evento **4740** fica no controlador de domínio PDC Emulator:

```powershell
$pdc = (Get-ADDomain).PDCEmulator
Get-WinEvent -ComputerName $pdc -FilterHashtable @{LogName='Security'; Id=4740; StartTime=(Get-Date).AddDays(-1)} | Where-Object { $_.Message -match 'usuario' } | Select-Object -First 5 TimeCreated,Message
```

   O campo **Caller Computer Name** mostra a máquina ou o serviço que está errando a senha.
4. Causas comuns na origem: senha antiga salva no **Gerenciador de Credenciais**, unidade de rede mapeada, tarefa agendada ou serviço rodando com a conta, celular com e-mail corporativo, sessão RDP aberta.
5. Corrija a credencial antiga e só então desbloqueie de novo. Confirme com `Get-ADUser usuario -Properties LockedOut`.
6. Se não houver origem interna, pode ser tentativa de força bruta: veja os eventos 4625 do mesmo IP e, se confirmar, trate como incidente de segurança.
