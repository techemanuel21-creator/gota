// Tests the Gota VS Code extension against a mocked `vscode` module and a fake Gota server. Run with any Node (e.g. the one inside the playwright package).
const assert = require('assert');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');
const Module = require('module');

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'gota-ext-'));
process.env.APPDATA = tmp;
const cfgDir = path.join(tmp, 'Gota');
fs.mkdirSync(cfgDir, { recursive: true });

// ---------------------------------------------------------------- a fake Gota server (OpenAI-style, streaming)
let lastRequest = null;
const server = http.createServer((req, res) => {
  let body = '';
  req.on('data', (c) => body += c);
  req.on('end', () => {
    if (req.headers.authorization !== 'Bearer segredo') { res.writeHead(401); res.end('{}'); return; }
    if (req.url === '/health') { res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ ok: true, model_ready: true })); return; }
    lastRequest = JSON.parse(body);
    res.writeHead(200, { 'Content-Type': 'text/event-stream' });
    const reply = 'Claro:\n```python\ndef soma(a, b):\n    return a + b\n```';
    for (let i = 0; i < reply.length; i += 7) {
      res.write('data: ' + JSON.stringify({ choices: [{ delta: { content: reply.slice(i, i + 7) } }] }) + '\n\n');
    }
    res.write('data: [DONE]\n\n');
    res.end();
  });
});

// ---------------------------------------------------------------- the mocked editor
const calls = { diff: [], warnings: [], infos: [], edits: [], docs: [] };
const providers = {};
const commands = {};
let nextInput = '';
let nextChoice = 'Aplicar';
const selection = { isEmpty: false, active: { line: 0, character: 0 } };
const document = {
  languageId: 'python', fileName: 'C:\\proj\\soma.py',
  getText: (sel) => (sel ? 'def soma(a,b): return a+b' : 'def soma(a,b): return a+b\n'),
  offsetAt: () => 0
};
const editor = {
  document, selection, viewColumn: 1,
  edit: async (cb) => { cb({ replace: (range, text) => calls.edits.push(text) }); return true; }
};
const vscode = {
  window: {
    activeTextEditor: editor,
    createOutputChannel: () => ({ dispose() {} }),
    createStatusBarItem: () => ({ show() {}, dispose() {} }),
    showInputBox: async () => nextInput,
    showInformationMessage: async (m, ...opts) => { calls.infos.push(m); return opts.includes(nextChoice) ? nextChoice : undefined; },
    showWarningMessage: async (m) => { calls.warnings.push(m); },
    showErrorMessage: async (m) => { calls.warnings.push(m); },
    showTextDocument: async () => {},
    withProgress: async (opts, fn) => fn()
  },
  commands: {
    registerCommand: (id, fn) => { commands[id] = fn; return { dispose() {} }; },
    executeCommand: async (...args) => { calls.diff.push(args); }
  },
  workspace: {
    registerTextDocumentContentProvider: (scheme, provider) => { providers[scheme] = provider; return { dispose() {} }; },
    openTextDocument: async (o) => { calls.docs.push(o); return {}; }
  },
  Uri: { parse: (s) => { const m = /^([^:]+):(\/.*)$/.exec(s); return { scheme: m[1], path: m[2], toString: () => s }; } },
  Range: class { constructor(a, b) { this.start = a; this.end = b; } },
  StatusBarAlignment: { Right: 2 }, ProgressLocation: { Notification: 15 }, ViewColumn: { Beside: -2 }
};
const realLoad = Module._load;
Module._load = function (request, ...rest) { return request === 'vscode' ? vscode : realLoad.call(this, request, ...rest); };

(async () => {
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  fs.writeFileSync(path.join(cfgDir, 'vscode.json'), JSON.stringify({ port: server.address().port, token: 'segredo' }));
  const ext = require('../vscode-extension/gota-vscode/extension.js');
  const subscriptions = [];
  ext.activate({ subscriptions });
  const results = [];
  const check = (name, fn) => { try { fn(); results.push('OK   ' + name); } catch (e) { results.push('FAIL ' + name + ' -> ' + e.message); process.exitCode = 1; } };

  // 1) fix: asks the server, shows a diff, applies after "Aplicar"
  nextInput = 'tratar tipos errados';
  await commands['gota.fix']();
  check('o pedido chegou ao servidor com a linguagem e o código', () => {
    const user = lastRequest.messages[lastRequest.messages.length - 1].content;
    assert(user.includes('python') && user.includes('def soma(a,b)') && user.includes('tratar tipos errados'));
    assert.strictEqual(lastRequest.messages[0].role, 'system');
  });
  check('a comparação foi aberta com original e proposta', () => {
    const [cmd, left, right] = calls.diff[0];
    assert.strictEqual(cmd, 'vscode.diff');
    assert.strictEqual(providers['gota-proposta'].provideTextDocumentContent(left), 'def soma(a,b): return a+b');
    assert.strictEqual(providers['gota-proposta'].provideTextDocumentContent(right), 'def soma(a, b):\n    return a + b');
  });
  check('a mudança só foi aplicada depois da confirmação', () => assert.deepStrictEqual(calls.edits, ['def soma(a, b):\n    return a + b']));

  // 2) "Descartar" must not change the file
  calls.edits.length = 0; nextChoice = 'Descartar'; nextInput = '';
  await commands['gota.refactor']();
  check('descartar não altera o arquivo', () => assert.strictEqual(calls.edits.length, 0));

  // 3) tests open a new document with the code only
  await commands['gota.tests']();
  check('testes abrem um documento novo só com o código', () => assert.strictEqual(calls.docs[calls.docs.length - 1].content, 'def soma(a, b):\n    return a + b\n'));

  // 4) code extraction
  check('extrai bloco fechado e bloco aberto', () => {
    assert.strictEqual(ext._test.codeFrom('x\n```js\na();\n```\ny'), 'a();');
    assert.strictEqual(ext._test.codeFrom('x\n```js\na();\nb();'), 'a();\nb();');
    assert.strictEqual(ext._test.codeFrom('sem bloco'), 'sem bloco');
  });

  // 5) Gota off (no connection file): a friendly warning, no crash
  fs.unlinkSync(path.join(cfgDir, 'vscode.json'));
  calls.warnings.length = 0; nextChoice = 'Aplicar';
  await commands['gota.explain']();
  check('com o Gota desligado avisa em vez de falhar', () => assert(calls.warnings.some((w) => w.includes('não está ligado'))));

  console.log(results.join('\n'));
  ext.deactivate();
  server.close();
  process.exit(process.exitCode || 0);
})().catch((e) => { console.error('ERRO NO TESTE', e); process.exit(1); });
