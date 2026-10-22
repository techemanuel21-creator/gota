# Programação: linguagens, idiomas, armadilhas e comandos
Fonte: conhecimento base do Gota

## Python
- Tipos: int, float, str, list, tuple, dict, set, bool, None. List/dict comprehension, f-strings, `with` (context managers), generators (`yield`), decorators, dataclasses, type hints, `pathlib`, `argparse`, `logging`, `venv` (`python -m venv .venv`), `pip install -r requirements.txt`, `pytest`, `unittest`.
- Armadilhas: argumentos padrão mutáveis (`def f(x=[])`), cópia rasa x profunda, `is` x `==`, escopo (`global/nonlocal`), GIL (use multiprocessing ou asyncio/threads para I/O), indentação mista, encoding (`open(..., encoding="utf-8")`).
- Útil: `subprocess.run([...], capture_output=True, text=True)`, `json`, `csv`, `sqlite3`, `requests`/`httpx`, `asyncio`, `concurrent.futures`, FastAPI/Flask/Django, pandas, numpy.

## JavaScript / TypeScript / Node
- `let/const`, arrow functions, `async/await`, Promises, módulos ES (`import/export`), destructuring, spread, `map/filter/reduce`, igualdade estrita `===`, `this` e closures. Node: `npm init/install`, `package.json`, `node --watch`, Express/Fastify, `fs/promises`, `process.env`.
- TypeScript: tipos, interfaces, generics, `strict`, `tsc --noEmit`, narrowing, `unknown` em vez de `any`.
- Front-end: DOM, eventos, fetch, CORS, React (hooks `useState/useEffect`, chaves em listas), Vue, Angular, bundlers (Vite), CSS (flex, grid, variáveis), acessibilidade.

## Java / Kotlin / C#
- Java: classes, interfaces, generics, streams, `Optional`, exceções checked, Maven/Gradle, JVM (heap `-Xmx`, GC), Spring Boot. Kotlin: null safety, data class, coroutines, extension functions, Android (Activity, ViewModel, Compose).
- C#/.NET: `async/await`, LINQ, records, DI nativa, ASP.NET Core, Entity Framework, NuGet, `dotnet build/run/test/publish`.

## C / C++ / Rust / Go
- C: ponteiros, `malloc/free`, buffer overflow, `const`, `static`, `make`/CMake, valgrind/ASan. C++: RAII, smart pointers (`unique_ptr`, `shared_ptr`), STL, move semantics, templates.
- Rust: ownership/borrowing/lifetimes, `Result/Option`, `cargo build/test/run`, crates, traits, `?`.
- Go: goroutines, channels, `defer`, interfaces, `error` explícito, `go mod`, `go test`, `go vet`, `context`.

## Scripts: Bash, PowerShell, SQL
- Bash: `set -euo pipefail`, aspas em `"$var"`, `[[ ]]`, `for f in *.log; do`, `$(cmd)`, pipes, `trap`, `getopts`.
- PowerShell: objetos no pipeline, `Where-Object/Select-Object/ForEach-Object`, `Get-Help`, `try/catch`, `-WhatIf/-Confirm`, módulos, `Invoke-RestMethod`, `ConvertFrom-Json`, `Export-Csv`.
- SQL: `SELECT/JOIN/GROUP BY/HAVING/ORDER BY`, índices, transações (ACID), normalização, `EXPLAIN`, evitar `SELECT *` e N+1, parâmetros (nunca concatenar strings: injeção SQL), `window functions`, CTEs; diferenças entre SQL Server (T-SQL), PostgreSQL, MySQL, SQLite, Oracle.

## PHP, Ruby, Perl, Lua, outros
PHP (Laravel, PDO com prepared statements), Ruby (Rails), Lua (embutido, jogos), R/Julia (dados), Swift (iOS), Dart/Flutter, assembly básico (registradores, pilha). HTML/CSS/XML/JSON/YAML/TOML: sintaxe e validação; regex (grupos, âncoras, quantificadores gananciosos x preguiçosos).

## Algoritmos e estruturas
Complexidade (O(1), O(log n), O(n), O(n log n), O(n²)), arrays, listas, pilhas, filas, hash maps, árvores, heaps, grafos (BFS/DFS, Dijkstra), ordenação, busca binária, programação dinâmica, recursão e memoização. Escolha estrutura pelo padrão de acesso.

## Depuração (qualquer linguagem)
Reproduzir o erro mínimo, ler a mensagem e a pilha de baixo para cima até o seu código, imprimir/logar valores, usar depurador (breakpoints, watch), bisect (`git bisect`), isolar dependências, verificar versões, ler a documentação oficial da API usada, escrever teste que falha antes de corrigir.
