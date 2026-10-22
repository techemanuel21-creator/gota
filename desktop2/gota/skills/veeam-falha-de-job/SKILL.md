---
name: veeam-falha-de-job
description: Use quando um job de backup do Veeam Backup & Replication terminar com falha ou aviso (Failed, Warning).
keywords: veeam, backup, job, falha, erro, warning, failed, vss, snapshot, repositório, cbt, credenciais, restauração
---
# Diagnóstico de job do Veeam com falha

1. Abra o job em **Home > Jobs** e dê dois cliques na sessão com falha. Leia a **primeira linha vermelha** de cada VM ou objeto: ela é a causa; as seguintes costumam ser consequência.
2. Classifique o erro:
   - **VSS / snapshot** ("Failed to create VSS snapshot", "VSS_E_..."): no servidor protegido rode `vssadmin list writers`. Writer com estado diferente de "Stable" pede reiniciar o serviço dele ou o servidor. Confira o espaço livre no volume (ao menos 10 a 15%) e `vssadmin list shadowstorage`.
   - **Repositório** ("not enough space", "access denied"): veja o espaço em **Backup Infrastructure > Backup Repositories**, a permissão da conta de serviço na pasta e se o compartilhamento está acessível.
   - **Credenciais ou rede** ("Cannot connect", "RPC", "access is denied"): teste ping e resolução de nome do host protegido, as portas entre os componentes (confirme na documentação da sua versão; costumam envolver 135, 445, 6160, 6162 e a faixa 2500-3300) e redigite a credencial em **Manage Credentials**.
   - **CBT** ("CBT data is invalid"): o Veeam reinicia o rastreamento e faz uma leitura completa no próximo ciclo; fica mais lento uma vez.
   - **Snapshot de VM preso ou muito antigo** (VMware ou Hyper-V): remova snapshots órfãos pelo vSphere ou Hyper-V Manager e rode o job de novo.
3. Se for erro de componente, leia o log em `C:\ProgramData\Veeam\Backup\<nome do job>\` (arquivos `Job.<nome>.Backup.log`) e procure por `Error` ou `Exception`.
4. Depois de corrigir, use **Retry** só nas VMs com falha (botão direito na sessão > Retry) e confirme que terminou em Success.
5. Se repetir, abra chamado com o pacote de logs (**Menu > Help > Support Information**).
