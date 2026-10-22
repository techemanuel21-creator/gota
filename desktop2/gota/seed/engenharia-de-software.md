# Engenharia de software: Git, CI/CD, contêineres, APIs, testes, arquitetura e segurança de código
Fonte: conhecimento base do Gota

## Git
```sh
git status ; git log --oneline --graph -20 ; git diff ; git diff --staged
git switch -c feature/x ; git add -p ; git commit -m "msg" ; git push -u origin feature/x
git pull --rebase ; git rebase -i HEAD~3   # (interativo só em terminal próprio)
git stash ; git stash pop ; git restore arquivo ; git restore --staged arquivo
git revert <sha>                           # desfaz por novo commit (seguro em branch compartilhada)
git reflog                                 # recupera commits "perdidos"
git bisect start ; git bisect bad ; git bisect good <sha>
git cherry-pick <sha> ; git tag -a v1.0 -m "release"
```
Conflito: abrir arquivo, resolver `<<<<<<<`, `git add`, `git rebase --continue` / `git commit`. Nunca `push --force` em branch compartilhada (use `--force-with-lease` só na sua). Segredo commitado: **revogue o segredo** primeiro, depois limpe o histórico (`git filter-repo`). `.gitignore` para binários, `.env`, `node_modules`.

## CI/CD
Pipeline: build → testes → análise estática/segurança → artefato → deploy (staging → produção). GitHub Actions (`.github/workflows/*.yml`), GitLab CI (`.gitlab-ci.yml`), Jenkins, Azure DevOps. Cache de dependências, matriz de versões, segredos em cofre do CI, deploy com **rollback**, **blue/green**, **canary**, feature flags. Versionamento semântico (MAJOR.MINOR.PATCH).

## Docker e Kubernetes
- Dockerfile: imagem base pequena, multi-stage build, `COPY` seletivo, usuário não root, `HEALTHCHECK`, `.dockerignore`, fixar versões. `docker build -t app .`, `docker run -p 8080:80 -v dados:/data app`, `docker logs -f`, `docker compose up -d`. Dados persistem só em volumes.
- Kubernetes: Pod, Deployment, Service (ClusterIP/NodePort/LB), Ingress, ConfigMap/Secret, PV/PVC, probes (liveness/readiness), requests/limits, HPA, namespaces, RBAC, NetworkPolicy. Diagnóstico: `kubectl describe pod`, `logs --previous`, `get events --sort-by=.lastTimestamp`, `top pods`.

## APIs e arquitetura
- REST (recursos, verbos, códigos 200/201/204/400/401/403/404/409/429/500/502/503), JSON, paginação, idempotência, versionamento, OpenAPI; GraphQL, gRPC, WebSocket, webhooks. Autenticação: API key, OAuth2/OIDC, JWT (validar assinatura/expiração; não guardar segredo no cliente), mTLS.
- Arquiteturas: monólito modular, microsserviços (complexidade operacional), event-driven (filas: RabbitMQ, Kafka, SQS), CQRS, hexagonal/clean architecture, 12-factor. Princípios: SOLID, DRY, KISS, separação de responsabilidades, baixo acoplamento.
- Dados: SQL (consistência) x NoSQL (documentos, chave-valor, colunar, grafo); cache (Redis) com invalidação definida; migrations versionadas; backups e teste de restauração.
- Resiliência: timeouts, retries com backoff exponencial + jitter, circuit breaker, idempotência, filas de mensagens mortas, observabilidade (logs estruturados, métricas, tracing OpenTelemetry).

## Testes e qualidade
Pirâmide: muitos testes unitários, alguns de integração, poucos E2E. Mocks só nas bordas, testes determinísticos, nomes que descrevem comportamento, cobertura como indicador (não meta absoluta). Linters/formatadores (ruff/black, eslint/prettier, gofmt, clippy), revisão de código, tipagem estática, TDD quando fizer sentido.

## Segurança de código
Validar entrada, escapar saída, consultas parametrizadas, hash de senha forte (argon2/bcrypt), não logar segredos, dependências atualizadas (Dependabot/Renovate, `npm audit`, `pip-audit`), SAST/SCA, segredos fora do repositório, CSRF/XSS/SSRF/IDOR, limitar taxa, CORS restrito, cabeçalhos (CSP, HSTS), princípio do menor privilégio em tokens e contas de serviço, SBOM, assinar artefatos.

## Desempenho
Meça antes (profiler: cProfile, py-spy, Chrome DevTools, pprof, perf), ache o gargalo (CPU, memória, I/O, rede, banco), otimize o algoritmo e o acesso a dados (índices, N+1, cache, paginação, batch) antes de micro-otimizar. Memória: vazamentos (referências retidas), tamanho de heap, GC.

## Licenças (para venda de software)
Permissivas: MIT, BSD, Apache-2.0 (permitem uso comercial; mantenha avisos). Copyleft: GPL/AGPL (exigem abrir código derivado se distribuir/oferecer em rede), LGPL (ligação dinâmica permitida). Verifique também a licença de **modelos de IA** e de **vozes/dados** usados; mantenha arquivo NOTICE/THIRD-PARTY com os avisos.
