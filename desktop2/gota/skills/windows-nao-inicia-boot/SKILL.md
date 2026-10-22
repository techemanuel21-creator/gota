---
name: windows-nao-inicia-boot
description: Use quando um Windows ou Windows Server não iniciar, entrar em reparo automático ou der tela azul no boot.
keywords: windows, boot, não inicia, bcd, bootrec, tela azul, bsod, reparo automático, bitlocker, chkdsk, sfc
---
# Windows não inicia

1. Anote a mensagem ou o **código da tela azul**. Se pedir chave do BitLocker, localize-a na conta Microsoft/AD antes de mexer em qualquer coisa.
2. Entre no **WinRE** (mídia de instalação > Reparar o computador > Prompt de comando).
3. Disco e arquivos: `chkdsk C: /f`, `sfc /scannow /offbootdir=C:\ /offwindir=C:\Windows`, `DISM /Image:C:\ /Cleanup-Image /RestoreHealth`.
4. Boot: `bootrec /fixmbr`, `bootrec /fixboot`, `bootrec /scanos`, `bootrec /rebuildbcd`; em UEFI recrie com `bcdboot C:\Windows`.
5. Driver ou atualização recente: desinstale a última atualização (`dism /image:C:\ /get-packages` e `/remove-package`) ou use ponto de restauração; modo de segurança.
6. Hardware: teste RAM (mdsched), SMART do disco, desconecte periféricos. Em VM, verifique controladora/disco virtual e snapshots.
7. Analise minidump em `C:\Windows\Minidump` (WinDbg `!analyze -v`). Se nada resolver, restaure do backup para uma cópia e valide antes de substituir.
