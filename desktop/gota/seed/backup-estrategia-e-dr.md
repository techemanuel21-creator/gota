# Estratégia de backup, recuperação de desastres (DR) e continuidade
Fonte: conhecimento base do Gota

## Conceitos
- **RPO** (quanto de dado se aceita perder, em tempo), **RTO** (quanto tempo para voltar), **RTA** (tempo real medido), **MTD/MAO** (tempo máximo tolerável de parada).
- **Backup não é replicação nem snapshot**: replicação copia também o erro/ransomware; snapshot depende do mesmo storage. Backup precisa de cópia independente, retenção e teste de restauração.
- Tipos: **full**, **incremental** (desde o último), **diferencial** (desde o último full), **full sintético** (monta full a partir de incrementais), **forever incremental**.
- **3-2-1** (3 cópias, 2 mídias, 1 fora do local) e **3-2-1-1-0** (mais 1 offline/imutável e 0 erros na verificação).
- Retenção **GFS** (avô-pai-filho): diários curtos, semanais, mensais, anuais conforme requisito legal/negócio.
- **Imutabilidade**: object lock (S3), repositório Linux hardened, WORM, fita offline. **Air gap**: cópia sem caminho de rede permanente.

## Ransomware e backup
- Atacantes procuram e apagam backups: separe credenciais, desligue o acesso do domínio ao repositório, use MFA, rede de backup segmentada, repositório imutável, contas de serviço mínimas.
- Teste regularmente a restauração completa (e o **tempo** que leva). Documente o **runbook** de DR: ordem de subida (DNS/AD primeiro, depois banco, depois aplicações), contatos, senhas de emergência guardadas offline.
- Antes de restaurar após incidente: contenção, erradicação, ponto limpo (anterior à infecção), restauração isolada, varredura, reconexão controlada.

## Planejamento
1. Inventário e criticidade (BIA): o que é crítico, dependências, RPO/RTO por sistema.
2. Escolher método por carga: VMs (nível hypervisor), bancos (log shipping/transaction log, dumps nativos), arquivos/NAS, SaaS (M365), físicos (agente), bancos grandes (snapshots de storage + backup).
3. Capacidade: dados protegidos × taxa de mudança × retenção × fator de compressão/dedup. Reserve crescimento e espaço de merge.
4. Janela e rede: banda efetiva, janela noturna, replicação para o site secundário.
5. Verificação: SureBackup/teste de boot, restauração de arquivos amostrais, verificação de integridade (health check).
6. Monitoramento e alertas: falhas, jobs não executados, espaço, retenção, licença.

## DR e alta disponibilidade
- **HA** (reinicia VMs ao cair um host: vSphere HA, cluster Hyper-V, Nutanix) ≠ **DR** (recuperar o site). Há também FT (tolerância a falhas), réplica assíncrona/síncrona, stretched cluster, Site Recovery (vSphere Replication, Veeam Replication, Azure Site Recovery, Zerto).
- **Failover/failback**, **planned failover**, **réplica com re-IP**, teste de DR sem interromper produção (rede isolada de teste).

## Checklist de um bom teste de restauração
Restaurar uma VM inteira em rede isolada, ligar, validar serviços e dados; restaurar arquivo avulso; restaurar um item de aplicação (e-mail, tabela, objeto AD); medir tempo; registrar resultado e corrigir o que falhou.
