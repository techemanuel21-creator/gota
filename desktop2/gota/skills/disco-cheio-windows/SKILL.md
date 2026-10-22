---
name: disco-cheio-windows
description: Use quando o disco C: (ou outro volume) do Windows está cheio ou quase cheio e é preciso achar e liberar espaço.
keywords: disco, cheio, espaço, c:, liberar, winsxs, temp, shadow, vss, dism, cleanmgr, hiberfil
---
# Disco cheio no Windows

1. Confirme o uso dos volumes:

```powershell
Get-PSDrive -PSProvider FileSystem | Select-Object Name,@{n='LivreGB';e={[math]::Round($_.Free/1GB,1)}},@{n='UsadoGB';e={[math]::Round($_.Used/1GB,1)}}
```

2. Ache as pastas grandes na raiz do volume:

```powershell
Get-ChildItem C:\ -Directory -Force -ErrorAction SilentlyContinue | ForEach-Object { [pscustomobject]@{GB=[math]::Round((Get-ChildItem $_.FullName -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum/1GB,2); Pasta=$_.FullName} } | Sort-Object GB -Descending | Select-Object -First 10
```

3. Costuma ser seguro limpar: pastas Temp (`$env:TEMP`, `C:\Windows\Temp`), o cache do Windows Update (pare o serviço `wuauserv`, apague `C:\Windows\SoftwareDistribution\Download\*` e inicie o serviço) e a Lixeira.
4. Componentes do Windows: `Dism /Online /Cleanup-Image /StartComponentCleanup`. Não apague a pasta WinSxS na mão.
5. Cópias de sombra ocupando espaço: `vssadmin list shadowstorage`. Para limitar: `vssadmin resize shadowstorage /for=C: /on=C: /maxsize=10GB`.
6. Hibernação sem uso: `powercfg /h off` libera o hiberfil.sys.
7. Antes de apagar arquivos de usuários ou dados de aplicações, confirme com o dono e prefira mover para outro disco.
