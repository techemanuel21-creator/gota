// Gota for VS Code: talks to the Gota desktop app on this computer (127.0.0.1). The model runs offline inside Gota; nothing leaves the PC.
// Reads the port and the secret token from %APPDATA%/Gota/vscode.json, which Gota writes while "Integração com o VS Code" is on.
const vscode = require('vscode');
const http = require('http');
const fs = require('fs');
const os = require('os');
const path = require('path');

const SCHEME = 'gota-proposta';
const MAX_CONTEXT = 7000;   // characters of code sent along with a request (the local model has a small window)
const docs = new Map();     // virtual documents shown in the diff view
let statusItem, channel, timer;

function configPath() {
  const appdata = process.env.APPDATA || path.join(os.homedir(), 'AppData', 'Roaming');
  return path.join(appdata, 'Gota', 'vscode.json');
}

function readConfig() {
  try { return JSON.parse(fs.readFileSync(configPath(), 'utf8')); } catch (e) { return null; }
}

function request(method, route, body, onDelta) {
  return new Promise((resolve, reject) => {
    const cfg = readConfig();
    if (!cfg) { reject(new Error('OFF')); return; }
    const data = body ? Buffer.from(JSON.stringify(body)) : null;
    const req = http.request({
      host: '127.0.0.1', port: cfg.port, path: route, method,
      headers: Object.assign({ Authorization: 'Bearer ' + cfg.token }, data ? { 'Content-Type': 'application/json', 'Content-Length': data.length } : {})
    }, (res) => {
      let buf = '', answer = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => {
        buf += chunk;
        if (body && body.stream) {
          let i;
          while ((i = buf.indexOf('\n\n')) >= 0) {
            const line = buf.slice(0, i); buf = buf.slice(i + 2);
            if (!line.startsWith('data: ') || line.includes('[DONE]')) continue;
            try {
              const piece = (JSON.parse(line.slice(6)).choices[0].delta || {}).content || '';
              if (piece) { answer += piece; if (onDelta) onDelta(answer); }
            } catch (e) { /* half a line: wait for the rest */ }
          }
        }
      });
      res.on('end', () => {
        if (res.statusCode >= 400) {
          let msg = 'HTTP ' + res.statusCode;
          try { msg = JSON.parse(buf).error.message || msg; } catch (e) { /* keep the status */ }
          reject(new Error(msg)); return;
        }
        if (body && body.stream) { resolve(answer); return; }
        try { resolve(JSON.parse(buf)); } catch (e) { reject(e); }
      });
    });
    req.on('error', () => reject(new Error('OFF')));
    if (data) req.write(data);
    req.end();
  });
}

async function ask(messages, onDelta) {
  return request('POST', '/v1/chat/completions', { model: 'gota', stream: true, messages }, onDelta);
}

function explainFailure(e) {
  if (e && e.message === 'OFF') {
    vscode.window.showWarningMessage('O Gota não está ligado. Abra o Gota e ative “Integração com o VS Code” no menu Conexões.');
  } else if (e && /loading/i.test(e.message || '')) {
    vscode.window.showInformationMessage('O Gota ainda está acordando o modelo. Tente de novo em alguns segundos.');
  } else {
    vscode.window.showErrorMessage('Gota: ' + (e && e.message ? e.message : e));
  }
}

function codeFrom(text) {
  const m = /```[\w+#.-]*[ \t]*\r?\n([\s\S]*?)```/.exec(text);
  if (m) return m[1].replace(/\s+$/, '');
  const open = /```[\w+#.-]*[ \t]*\r?\n([\s\S]*)$/.exec(text);   // the model stopped before closing the block
  return (open ? open[1] : text).replace(/\s+$/, '');
}

function codeContext(editor) {
  const doc = editor.document;
  const sel = editor.selection;
  const picked = sel.isEmpty ? '' : doc.getText(sel);
  let around = '';
  if (!picked) {
    const text = doc.getText();
    around = text.length <= MAX_CONTEXT ? text : text.slice(Math.max(0, doc.offsetAt(sel.active) - MAX_CONTEXT / 2), doc.offsetAt(sel.active) + MAX_CONTEXT / 2);
  }
  return { language: doc.languageId, file: path.basename(doc.fileName), selected: picked.slice(0, MAX_CONTEXT), around, hasSelection: !!picked };
}

const SYSTEM_CODE = 'Você é um programador sênior. Responda em português do Brasil. Quando devolver código, devolva SOMENTE o código final dentro de UM bloco ``` com a linguagem, sem explicações antes ou depois, preservando o estilo e a indentação do código original.';
const SYSTEM_TALK = 'Você é um programador sênior que explica com clareza, em português do Brasil, de forma objetiva. Use blocos ``` para trechos de código.';

async function withProgress(title, fn) {
  return vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title, cancellable: false }, fn);
}

async function showMarkdown(content) {
  const doc = await vscode.workspace.openTextDocument({ language: 'markdown', content });
  await vscode.window.showTextDocument(doc, { viewColumn: vscode.ViewColumn.Beside, preview: false });
}

// ---- proposals: show the model's code next to the original and apply only if the user agrees
async function propose(editor, original, proposed, title, range) {
  const id = String(Date.now());
  docs.set(id + '/original', original);
  docs.set(id + '/proposta', proposed);
  const left = vscode.Uri.parse(`${SCHEME}:/${id}/original`);
  const right = vscode.Uri.parse(`${SCHEME}:/${id}/proposta`);
  await vscode.commands.executeCommand('vscode.diff', left, right, title);
  const choice = await vscode.window.showInformationMessage('Aplicar a mudança proposta pelo Gota?', 'Aplicar', 'Descartar');
  if (choice === 'Aplicar') {
    await vscode.window.showTextDocument(editor.document, editor.viewColumn);
    const ok = await editor.edit((b) => b.replace(range, proposed));
    if (!ok) vscode.window.showWarningMessage('Não consegui aplicar a mudança (o arquivo mudou?).');
  }
  while (docs.size > 40) docs.delete(docs.keys().next().value);   // keep the latest proposals: the diff tab may ask for its content again
}

function needEditor() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) vscode.window.showInformationMessage('Abra um arquivo primeiro.');
  return editor;
}

async function transform(kind, instruction) {
  const editor = needEditor(); if (!editor) return;
  const c = codeContext(editor);
  if (!c.hasSelection) { vscode.window.showInformationMessage('Selecione o trecho de código primeiro.'); return; }
  const task = {
    fix: 'Corrija os erros e melhore este código' + (instruction ? ': ' + instruction : '') + '.',
    refactor: 'Refatore este código deixando-o mais claro e simples, sem mudar o comportamento' + (instruction ? '. ' + instruction : '') + '.',
    docs: 'Acrescente documentação (docstring ou comentários no padrão da linguagem) a este código, sem mudar a lógica.'
  }[kind];
  try {
    const answer = await withProgress('Gota está trabalhando no código…', () => ask([
      { role: 'system', content: SYSTEM_CODE },
      { role: 'user', content: `${task}\nLinguagem: ${c.language}. Arquivo: ${c.file}.\n\n\`\`\`${c.language}\n${c.selected}\n\`\`\`` }
    ]));
    const proposed = codeFrom(answer);
    if (!proposed.trim()) { vscode.window.showWarningMessage('O Gota não devolveu código. Tente descrever melhor o pedido.'); return; }
    await propose(editor, c.selected, proposed, 'Gota: proposta (original ↔ novo)', editor.selection);
  } catch (e) { explainFailure(e); }
}

function activate(context) {
  channel = vscode.window.createOutputChannel('Gota');
  context.subscriptions.push(channel);
  context.subscriptions.push(vscode.workspace.registerTextDocumentContentProvider(SCHEME, {
    provideTextDocumentContent: (uri) => docs.get(uri.path.replace(/^\//, '')) || ''
  }));

  statusItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 50);
  statusItem.command = 'gota.ask';
  context.subscriptions.push(statusItem);
  const refresh = async () => {
    try {
      const h = await request('GET', '/health');
      statusItem.text = h.model_ready ? '$(hubot) Gota' : '$(sync~spin) Gota carregando';
      statusItem.tooltip = h.model_ready ? 'Gota conectado (modelo local). Clique para perguntar.' : 'O Gota está carregando o modelo.';
    } catch (e) {
      statusItem.text = '$(circle-slash) Gota desligado';
      statusItem.tooltip = 'Abra o Gota e ative “Integração com o VS Code” em Conexões.';
    }
    statusItem.show();
  };
  refresh();
  timer = setInterval(refresh, 15000);
  context.subscriptions.push({ dispose: () => clearInterval(timer) });

  const reg = (id, fn) => context.subscriptions.push(vscode.commands.registerCommand(id, fn));

  reg('gota.ask', async () => {
    const q = await vscode.window.showInputBox({ prompt: 'Pergunte ao Gota (ele vê o trecho selecionado ou o arquivo aberto)', placeHolder: 'ex.: por que esta função retorna None?' });
    if (!q) return;
    const editor = vscode.window.activeTextEditor;
    let body = q;
    if (editor) {
      const c = codeContext(editor);
      const code = c.hasSelection ? c.selected : c.around;
      body = `${q}\n\nArquivo: ${c.file} (${c.language})${c.hasSelection ? ', trecho selecionado' : ''}:\n\n\`\`\`${c.language}\n${code}\n\`\`\``;
    }
    try {
      const answer = await withProgress('Gota está pensando…', () => ask([{ role: 'system', content: SYSTEM_TALK }, { role: 'user', content: body }]));
      await showMarkdown(`# Pergunta\n\n${q}\n\n# Resposta do Gota\n\n${answer}\n`);
    } catch (e) { explainFailure(e); }
  });

  reg('gota.explain', async () => {
    const editor = needEditor(); if (!editor) return;
    const c = codeContext(editor);
    const code = c.hasSelection ? c.selected : c.around;
    try {
      const answer = await withProgress('Gota está lendo o código…', () => ask([
        { role: 'system', content: SYSTEM_TALK },
        { role: 'user', content: `Explique este código (${c.language}, ${c.file}): o que faz, a lógica principal e qualquer problema que você note.\n\n\`\`\`${c.language}\n${code}\n\`\`\`` }
      ]));
      await showMarkdown(`# Explicação de ${c.file}\n\n${answer}\n`);
    } catch (e) { explainFailure(e); }
  });

  reg('gota.fix', async () => {
    const what = await vscode.window.showInputBox({ prompt: 'O que corrigir ou melhorar? (pode deixar vazio)', placeHolder: 'ex.: tratar o erro quando o arquivo não existe' });
    if (what === undefined) return;
    await transform('fix', what);
  });
  reg('gota.refactor', async () => { await transform('refactor', ''); });
  reg('gota.docs', async () => { await transform('docs', ''); });

  reg('gota.tests', async () => {
    const editor = needEditor(); if (!editor) return;
    const c = codeContext(editor);
    if (!c.hasSelection) { vscode.window.showInformationMessage('Selecione o código que será testado.'); return; }
    try {
      const answer = await withProgress('Gota está escrevendo os testes…', () => ask([
        { role: 'system', content: SYSTEM_CODE },
        { role: 'user', content: `Escreva testes automatizados para este código usando o framework de testes mais comum de ${c.language}. Inclua casos normais e de borda.\n\n\`\`\`${c.language}\n${c.selected}\n\`\`\`` }
      ]));
      const doc = await vscode.workspace.openTextDocument({ language: c.language, content: codeFrom(answer) + '\n' });
      await vscode.window.showTextDocument(doc, { viewColumn: vscode.ViewColumn.Beside, preview: false });
    } catch (e) { explainFailure(e); }
  });

  reg('gota.generate', async () => {
    const editor = needEditor(); if (!editor) return;
    const what = await vscode.window.showInputBox({ prompt: 'Descreva o código que o Gota deve escrever aqui', placeHolder: 'ex.: função que lê um CSV e devolve a soma da coluna valor' });
    if (!what) return;
    const c = codeContext(editor);
    try {
      const answer = await withProgress('Gota está escrevendo…', () => ask([
        { role: 'system', content: SYSTEM_CODE },
        { role: 'user', content: `Escreva em ${c.language}: ${what}\nArquivo: ${c.file}. Código ao redor (para seguir o estilo):\n\n\`\`\`${c.language}\n${c.around.slice(-2500)}\n\`\`\`` }
      ]));
      const proposed = codeFrom(answer);
      if (!proposed.trim()) { vscode.window.showWarningMessage('O Gota não devolveu código.'); return; }
      await propose(editor, '', proposed, 'Gota: código novo (vazio ↔ novo)', new vscode.Range(editor.selection.active, editor.selection.active));
    } catch (e) { explainFailure(e); }
  });
}

function deactivate() { if (timer) clearInterval(timer); }

module.exports = { activate, deactivate, _test: { codeFrom, codeContext, readConfig } };
