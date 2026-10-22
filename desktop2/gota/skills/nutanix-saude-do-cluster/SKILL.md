---
name: nutanix-saude-do-cluster
description: Use quando precisar verificar a saúde de um cluster Nutanix, alertas, data resiliency, CVM ou disco.
keywords: nutanix, ahv, prism, cvm, ncc, cluster, resiliency, disco, alerta, aos, lcm
---
# Nutanix: checar a saúde do cluster

1. No Prism Element: Home > **Data Resiliency Status** deve estar OK; veja alertas, espaço do storage pool (acima de 75% exige ação) e hosts/CVMs.
2. Na CVM (SSH como `nutanix`): `cluster status` (todos os serviços UP), `ncc health_checks run_all` (leia FAIL e WARN primeiro), `ncli cluster info`, `ncli disk list`, `allssh "df -h"`.
3. CVM fora do ar: o host continua, mas o cluster fica degradado; verifique disco/memória/rede, inicie a CVM e espere o cluster voltar a Resiliency OK antes de qualquer outra manutenção.
4. Disco falho: troque pelo Prism (Hardware > Diagram); acompanhe o rebuild. Nunca tire um segundo nó (em RF2) enquanto houver rebuild.
5. Antes de atualizar (LCM): rode o NCC, resolva alertas, mantenha capacidade para um nó fora, atualize um componente por vez.
6. Verifique NTP/DNS (horário errado quebra serviços), logs em `/home/nutanix/data/logs/` e, se persistir, abra chamado com o pacote de logs (Collect Logs).
