"""
Servidor local do `damfe setup`.

Um adaptador de entrada como o CLI: traduz requisição HTTP em caso de
uso e devolve o resultado. A diferença é a forma, não o papel — nenhuma
regra vive aqui.

Por que uma página, e não uma entrevista no terminal: o valor do setup
não está em perguntar, está em VER o que a resposta produziu. Declarar
um padrão e receber de volta "3 micro frontends, 12 telas" na mesma
tela é o que separa uma spec conferida de uma spec lida.

A chave nunca chega ao navegador. Quem fala com o provedor é este
servidor, usando o que `SettingsRepository` guardou; a página só manda
a chave uma vez, ao salvá-la, e recebe de volta a versão mascarada.

Escuta apenas em 127.0.0.1. Um servidor que aceita credencial não pode
aceitar conexão de fora da máquina.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from damfe.application.errors import ApplicationError
from damfe.application.settings import LlmSettings
from damfe.adapters.driven.storage.yaml_spec import (
    COMMUNICATION,
    SETUP_DIRECTORY,
)

#: Só o laço de retorno. Ver o cabeçalho do módulo.
HOST = "127.0.0.1"


def serve(
    container,
    repository: Path,
    port: int,
    open_browser: bool,
    write,
) -> int:

    state = _State(container, repository)

    handler = _make_handler(state)

    httpd = HTTPServer((HOST, port), handler)

    address = f"http://{HOST}:{httpd.server_port}/"

    write(f"Setup do damfe em {address}")
    write("Ctrl+C para encerrar.")

    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(address)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        write("\nEncerrado.")

    return 0


class _State:
    """O que o servidor precisa lembrar entre requisições."""

    def __init__(self, container, repository: Path):
        self.container = container
        self.repository = repository
        self.history: list[dict] = []


# ---------------------------------------------------------------- ações


def _mask(key: str) -> str:
    """Nunca devolve a chave inteira, nem para quem a digitou."""

    return f"…{key[-6:]}" if len(key) > 6 else ("definida" if key else "")


def _settings(state) -> LlmSettings:

    return state.container.settings.load_llm()


def _get_state(state, _payload) -> dict:

    llm = _settings(state)

    spec = state.container.specs.load_communication(state.repository)

    return {
        "repository": str(state.repository.resolve()),
        "key": _mask(llm.key),
        "model": llm.model or DEFAULT_MODEL,
        "models": [{"id": i, "paid": p} for i, p in MODELS],
        "mechanisms": [m.name for m in spec.mechanisms],
        "build": BUILD,
    }


def _save_key(state, payload) -> dict:
    """
    A página não pergunta o endereço: ela fala com o OpenRouter.

    Um provedor só tira uma decisão do caminho e evita o erro mais
    provável do setup — endereço base sem o caminho de conversa, que
    responde 404. Quem precisa de outro provedor continua servido por
    `damfe setup-llm`, que aceita `--url`.
    """

    state.container.setup_llm(
        endpoint=None,
        model=payload.get("model") or None,
        key=payload.get("key") or None,
    ).execute()

    return _get_state(state, None)


def _chat(state, payload) -> dict:
    """
    Repassa a conversa ao provedor, do lado do servidor.

    É aqui que o modelo entra, e só aqui: esta é a etapa de AUTORIA. O
    que ela produz é um arquivo que o usuário revisa e versiona. A
    análise, depois, lê o arquivo e não fala com ninguém.
    """

    llm = _settings(state)

    if not llm.key:
        raise ApplicationError("Set a credential before chatting.")

    state.history.append({"role": "user", "content": payload["message"]})

    body = json.dumps(
        {
            "model": llm.model,
            "messages": [{"role": "system", "content": _PROMPT}]
            + state.history,
        }
    ).encode()

    request = urllib.request.Request(
        _completions(llm.endpoint),
        data=body,
        headers={
            "Authorization": f"Bearer {llm.key}",
            "Content-Type": "application/json",
        },
    )

    # 429 é limite de taxa, e é a resposta normal de modelo gratuito:
    # eles compartilham uma cota pequena entre todo mundo. Vale
    # esperar e repetir, porque a janela costuma ser de segundos.
    answer = None

    for attempt in range(4):

        try:
            answer = json.load(
                urllib.request.urlopen(request, timeout=180)
            )
            break

        except urllib.error.HTTPError as error:

            if error.code == 429 and attempt < 3:
                time.sleep(4 * (attempt + 1))
                continue

            if error.code == 429:
                raise ApplicationError(
                    "The provider is rate limiting this key (429). "
                    "Free models share a small quota — wait a moment "
                    "or set a paid model in step 1."
                ) from error

            raise ApplicationError(
                f"The provider answered {error.code}."
            ) from error

        except Exception as error:
            raise ApplicationError(
                f"Could not reach the provider: {error}"
            )

    reply = answer["choices"][0]["message"]["content"]

    state.history.append({"role": "assistant", "content": reply})

    return {"reply": reply}


def _completions(endpoint: str) -> str:
    """
    O caminho de conversa a partir do endereço configurado.

    O que se guarda é a base — `https://openrouter.ai/api/v1` —,
    porque é o que os provedores documentam e o que o usuário tem à
    mão. Postar nela devolve 404: quem responde é `/chat/completions`.
    Quem já configurou o caminho inteiro não é penalizado por isso.
    """

    base = endpoint.rstrip("/")

    if base.endswith("/chat/completions"):
        return base

    return f"{base}/chat/completions"


def _save_spec(state, payload) -> dict:

    # O YAML é gravado como veio: ele foi revisado na tela, e
    # reserializá-lo a partir do modelo descartaria comentário e ordem
    # — justamente o que torna um arquivo versionado legível depois.
    destination = _spec_path(state)

    destination.parent.mkdir(parents=True, exist_ok=True)

    destination.write_text(payload["yaml"], encoding="utf-8")

    # Relê pelo caminho normal: se o arquivo não carregar, o erro
    # aparece agora, e não na próxima análise.
    state.container.specs.load_communication(state.repository)

    return {"written": str(destination)}


def _spec_path(state) -> Path:

    return (
        state.repository
        / SETUP_DIRECTORY
        / COMMUNICATION
    )


def _analyze(state, _payload) -> dict:
    """Roda a análise e devolve o suficiente para conferir a spec."""

    reconstructor = state.container.reconstructor(
        framework=None,
        repository_path=state.repository,
        organization_prefix=None,
    )

    if not reconstructor:
        raise ApplicationError(
            "No extractor recognised this repository."
        )

    artifacts = state.container.reconstruct(
        repository_path=state.repository,
        destination=state.repository / "artifacts",
        reconstructor=reconstructor,
    ).execute().artifacts

    detections = state.container.detect(
        source=state.repository / "artifacts",
        destination=None,
        rules=state.container.rules(None),
    ).execute().detections

    return {
        "extractor": reconstructor.name,
        "microfrontends": [m.id for m in artifacts.microfrontends],
        "screens": sum(len(m.screens) for m in artifacts.microfrontends),
        "fragments": sum(
            len(m.fragments) for m in artifacts.microfrontends
        ),
        "fragment_imports": len(artifacts.fragment_imports),
        "navigations": len(artifacts.navigations),
        "communications": len(artifacts.communications),
        "api_calls": len(artifacts.api_calls),
        "state_accesses": len(artifacts.state_accesses),
        "detections": [
            {"rule": d.rule, "message": d.message} for d in detections
        ],
    }


ACTIONS = {
    "/api/state": _get_state,
    "/api/key": _save_key,
    "/api/chat": _chat,
    "/api/spec": _save_spec,
    "/api/analyze": _analyze,
}


# ---------------------------------------------------------------- HTTP


def _make_handler(state):

    class Handler(BaseHTTPRequestHandler):

        def log_message(self, *_args):
            """Silencia o log por requisição, que só polui o terminal."""

        def _send(self, status: int, payload: dict) -> None:

            body = json.dumps(payload).encode()

            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):

            if self.path.startswith("/api/"):
                return self._run(self.path, {})

            page = PAGE.encode()

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            # A página vive dentro do processo: cada `damfe setup`
            # serve a versão da instalação atual. Deixar o navegador
            # guardá-la faz ele rodar o JS de uma versão anterior
            # contra a API da nova, e o sintoma é um campo preso em
            # "loading" que nenhuma correção no servidor desfaz.
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)

        def do_POST(self):

            length = int(self.headers.get("Content-Length") or 0)

            payload = json.loads(self.rfile.read(length) or b"{}")

            self._run(self.path, payload)

        def _run(self, path: str, payload: dict) -> None:

            action = ACTIONS.get(path.split("?")[0])

            if not action:
                return self._send(404, {"error": "not found"})

            try:
                self._send(200, action(state, payload))

            except ApplicationError as error:
                self._send(400, {"error": str(error)})

            except Exception as error:  # noqa: BLE001
                self._send(500, {"error": f"{type(error).__name__}: {error}"})

    return Handler


#: Modelos oferecidos na página, com a cobrança marcada.
#:
#: Lista fixa de propósito. Buscar o catálogo do OpenRouter a cada
#: carga traz centenas de entradas — quase nenhuma serve para conduzir
#: uma entrevista — e põe uma chamada de rede entre o usuário e a
#: primeira tela do setup.
#:
#: A distinção pago/gratuito fica visível porque é ela que explica o
#: erro mais comum daqui: modelo gratuito divide uma cota pequena
#: entre todos os usuários do provedor e responde 429 sob carga.
#:
#: Quem quiser outro modelo continua servido por `damfe setup-llm
#: --model`, que aceita qualquer identificador.
MODELS = (
    ("anthropic/claude-sonnet-4.5", True),
    ("anthropic/claude-opus-4.1", True),
    ("openai/gpt-5", True),
    ("openai/gpt-5-mini", True),
    ("google/gemini-2.5-pro", True),
    ("google/gemini-2.5-flash", True),
    ("deepseek/deepseek-v4-flash-0731:free", False),
    ("qwen/qwen3.8-27b:free", False),
    ("nvidia/nemotron-3.5-lightning:free", False),
    ("inclusionai/ling-3.0-flash-vl:free", False),
)

#: O padrão quando não há nada configurado.
DEFAULT_MODEL = "anthropic/claude-sonnet-4.5"


_PROMPT = """\
You are running the setup of a static-analysis tool for micro \
frontend architectures.

The user describes four things, and may leave any of them blank. A \
blank field is information: that technology may have no equivalent.

- DISCOVERY: how the micro frontends are declared, and where
- COMPOSITION: how one puts a piece of another inside its own screen
- ROUTING: how it is decided which one answers each URL
- COMMUNICATION: how one tells another that something happened

Run a short interview. Ask for a code example whenever the prose is \
not enough to identify the call, the module it comes from, and which \
argument carries the information.

When you have enough, answer with the final YAML in a code block:

discovery:
  file: <where to look, e.g. root-config/src/index.js>
  declares_unit:
    module: <where the call comes from, e.g. single-spa>
    call: <function name, e.g. registerApplication>
    name: {argument: <index>, field: <field of the object>}
    entrypoint: {argument: <index>, field: <field of the object>}

composition:
  consumes_fragment:
    form: <import | call>
    prefix: <what identifies another micro frontend's package>

routing:
  route_owner: {argument: <index>, field: <field of the object>}
  matching: <prefix-with-boundary | exact>

mechanisms:
  - name: <short name for the mechanism>
    kind: <event-bus | custom-event | post-message | store>
    produce:
      module: <import specifier, e.g. @org/bus>
      export: <name of the publishing function>
      channel_argument: <index of the argument holding the channel>
    consume:
      module: <import specifier>
      export: <name of the subscribing function>
      channel_argument: <index of the argument>

Include only the sections the user described. Never invent a \
mechanism, call or field they did not mention — when something is \
ambiguous, ask before generating. Always answer in English.
"""


#: Impressão digital da página servida, mostrada no rodapé do
#: cabeçalho. Calculada do próprio texto: muda quando a página muda.
def _build() -> str:

    import hashlib

    return hashlib.sha256(PAGE.encode()).hexdigest()[:8]


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>damfe Setup</title>
<style>
  :root {
    --fundo: #fbfaf8; --papel: #fff; --tinta: #1c1b1a;
    --suave: #6b6864; --linha: #e3e0db; --destaque: #0059dd;
    --alerta: #9b3a2a;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --fundo: #17181a; --papel: #1f2124; --tinta: #ecebe9;
      --suave: #9b9894; --linha: #32353a; --destaque: #6ba6ff;
      --alerta: #e0806c;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--fundo); color: var(--tinta);
    font: 17px/1.6 ui-sans-serif, system-ui, -apple-system, sans-serif;
    padding: 32px 16px 64px;
  }
  main { max-width: 820px; margin: 0 auto; }
  h1 { font-size: 1.55rem; margin: 0 0 4px; letter-spacing: -0.02em; }
  h2 { font-size: 1.15rem; margin: 0 0 6px; }
  .nota { font-size: .88rem; color: var(--suave); margin: 0 0 16px; }

  ol.passos {
    display: flex; gap: 8px; list-style: none; padding: 0;
    margin: 22px 0 18px; flex-wrap: wrap;
  }
  ol.passos li {
    display: flex; align-items: center; gap: 7px; font-size: .86rem;
    color: var(--suave); padding: 5px 12px 5px 6px;
    border: 1px solid var(--linha); border-radius: 999px;
  }
  ol.passos li b {
    width: 23px; height: 23px; border-radius: 50%; display: grid;
    place-items: center; background: var(--linha); color: var(--suave);
    font-size: .78rem; font-weight: 700;
  }
  ol.passos li[aria-current] { color: var(--tinta);
    border-color: var(--destaque); }
  ol.passos li[aria-current] b { background: var(--destaque);
    color: #fff; }
  ol.passos li[data-feito] b::after { content: "✓"; }
  ol.passos li[data-feito] b { font-size: .8rem; }
  ol.passos li[data-feito] b span { display: none; }

  .cartao { background: var(--papel); border: 1px solid var(--linha);
            border-radius: 11px; padding: 22px; }
  label { display: block; font-size: .84rem; color: var(--suave);
          margin-bottom: 5px; }
  input, textarea, select {
    width: 100%; padding: 9px 11px; border: 1px solid var(--linha);
    border-radius: 7px; background: var(--fundo); color: var(--tinta);
    font: inherit; margin-bottom: 12px;
  }
  textarea { font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
             font-size: 14.5px; min-height: 120px; resize: vertical; }
  button {
    background: var(--destaque); color: #fff; border: 0; padding: 9px 17px;
    border-radius: 7px; font: inherit; font-weight: 600; cursor: pointer;
  }
  button.leve { background: transparent; color: var(--destaque);
                border: 1px solid var(--linha); }
  button[disabled] { opacity: .45; cursor: default; }
  .linha { display: flex; gap: 10px; align-items: center;
           flex-wrap: wrap; }
  .rodape { display: flex; justify-content: space-between; gap: 10px;
            margin-top: 20px; padding-top: 16px;
            border-top: 1px solid var(--linha); }
  .erro { color: var(--alerta); font-size: .89rem; }
  #conversa { display: grid; gap: 10px; margin: 16px 0; }
  .msg { padding: 11px 14px; border-radius: 8px; white-space: pre-wrap;
         font-size: .94rem; border: 1px solid var(--linha); }
  .msg.user { background: var(--fundo); }
  table { width: 100%; border-collapse: collapse; font-size: .92rem; }
  td { padding: 6px 0; border-bottom: 1px solid var(--linha); }
  td:last-child { text-align: right; font-variant-numeric: tabular-nums; }
  code { font-family: ui-monospace, Menlo, monospace; font-size: .85em; }
  details.ja-pega { margin: 0 0 14px; font-size: .88rem; }
  details.ja-pega summary { cursor: pointer; color: var(--destaque); }
  details.ja-pega dl { margin: 10px 0 0; display: grid;
                       grid-template-columns: max-content 1fr;
                       gap: 6px 14px; align-items: baseline; }
  details.ja-pega dt { color: var(--suave); font-weight: 600;
                       font-size: .82rem; }
  details.ja-pega dd { margin: 0; }
  @media (max-width: 560px) {
    details.ja-pega dl { grid-template-columns: 1fr; gap: 2px; }
    details.ja-pega dt { margin-top: 8px; }
    .rodape { flex-direction: column-reverse; }
    .rodape button { width: 100%; }
  }
  [hidden] { display: none !important; }
</style>
</head>
<body>
<main>

  <h1>damfe Setup</h1>
  <p class="nota" id="repo">…</p>
  <p class="nota" id="build" style="margin:-12px 0 0; opacity:.6"></p>

  <ol class="passos">
    <li data-passo="0"><b><span>1</span></b> Model access</li>
    <li data-passo="1"><b><span>2</span></b> How this system works</li>
    <li data-passo="2"><b><span>3</span></b> Check</li>
  </ol>

  <!-- ------------------------------------------------ 1 -->
  <section class="cartao" data-painel="0">
    <h2>Model access</h2>
    <p class="nota">The agent runs the interview in the next step, so
      its credential comes first. Setup talks to
      <a href="https://openrouter.ai/keys" target="_blank"
         rel="noreferrer">OpenRouter</a>, which fronts every major
      model behind one key. The key is kept in
      <code>~/.config/damfe/</code>, never in the analysed project,
      and never reaches the browser.</p>

    <label for="key">OpenRouter key</label>
    <input id="key" type="password" placeholder="sk-or-v1-…"
           autocomplete="off">
    <label for="model">Model</label>
    <select id="model"></select>

    <div class="rodape">
      <span class="nota" id="key-estado" style="margin:0"></span>
      <button id="ir-1">Save and continue</button>
    </div>
  </section>

  <!-- ------------------------------------------------ 2 -->
  <section class="cartao" data-painel="1" hidden>
    <h2>How this system works</h2>
    <p class="nota">Describe it in prose or paste code examples. Fill
      in what you know — the agent asks for the rest.</p>

    <label for="inventario">Micro Frontend Discovery — how the micro
      frontends are declared, and in which file</label>
    <textarea id="inventario" placeholder="e.g. the shell in root-config/src/index.js calls registerApplication() from single-spa once per micro frontend; the name is the object's name field…"></textarea>

    <label for="composicao">Composition — how one micro frontend puts
      a piece of another inside its own screen</label>
    <textarea id="composicao" placeholder="e.g. by importing the other's package directly — import Fragment from '@org/mfe-products/Fragment' — and rendering it as a component. Those packages stay as externals…"></textarea>

    <label for="roteamento">Routing — how it is decided which one
      answers each URL</label>
    <textarea id="roteamento" placeholder="e.g. each registration carries activeWhen with the route prefix; navigation uses navigateToUrl()…"></textarea>

    <label for="comunicacao">Communication — how one tells another
      that something happened</label>
    <details class="ja-pega">
      <summary>damfe already recognises these on its own — declare only
        what is not listed</summary>
      <dl>
        <dt>Platform primitives</dt>
        <dd><code>CustomEvent</code> with <code>dispatchEvent</code> and
          <code>addEventListener</code> · <code>BroadcastChannel</code>
          · <code>postMessage</code></dd>
        <dt>Known event buses</dt>
        <dd><code>mitt</code> · <code>eventemitter3</code> ·
          <code>tiny-emitter</code> · <code>pubsub-js</code></dd>
        <dt>Global state</dt>
        <dd><code>react-redux</code> · <code>zustand</code> ·
          <code>jotai</code> · <code>recoil</code> ·
          <code>mobx-react-lite</code> · <code>pinia</code>
          <span class="nota">(reads only; becomes an edge when two micro
          frontends read the same slice)</span></dd>
      </dl>
    </details>
    <textarea id="comunicacao" placeholder="e.g. our own bus at @org/bus, with publish(channel, data) and subscribe(channel, callback)…"></textarea>

    <div id="conversa"></div>

    <div id="seguir" hidden>
      <label for="mensagem">Reply</label>
      <textarea id="mensagem" style="min-height:80px"></textarea>
      <div class="linha">
        <button id="responder" class="leve">Reply</button>
      </div>
    </div>

    <div class="rodape">
      <button class="leve" data-voltar="0">Back</button>
      <div class="linha">
        <span class="erro" id="chat-erro"></span>
        <button id="enviar">Send and continue</button>
      </div>
    </div>
  </section>

  <!-- ------------------------------------------------ 3 -->
  <section class="cartao" data-painel="2" hidden>
    <h2>Check</h2>
    <p class="nota">Running the analysis is what checks the
      declaration. A spec reviewed by reading misleads; one checked
      against the result does not.</p>

    <div class="linha">
      <button id="rodar">Run analysis</button>
      <span class="nota" id="analise-estado" style="margin:0"></span>
    </div>

    <div id="resultado" hidden style="margin-top:16px"></div>

    <div class="rodape">
      <button class="leve" data-voltar="1">Back</button>
      <span></span>
    </div>
  </section>

</main>
<script>
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];

async function api(caminho, corpo) {
  const r = await fetch(caminho, corpo
    ? {method:'POST', headers:{'Content-Type':'application/json'},
       body: JSON.stringify(corpo)}
    : {});
  const d = await r.json();
  if (!r.ok) throw new Error(d.error || 'failed');
  return d;
}

// O passo 1 é porta: sem credencial o agente da etapa 2 não responde,
// e deixar avançar só adiaria o erro para depois do usuário escrever
// quatro campos.
let atual = 0, feitos = new Set();

function mostrar(n) {
  atual = n;
  $$('[data-painel]').forEach(p =>
    p.hidden = Number(p.dataset.painel) !== n);
  $$('ol.passos li').forEach(li => {
    const i = Number(li.dataset.passo);
    li.toggleAttribute('aria-current', i === n);
    li.toggleAttribute('data-feito', feitos.has(i) && i !== n);
  });
  window.scrollTo({top: 0, behavior: 'smooth'});
}

$$('[data-voltar]').forEach(b =>
  b.onclick = () => mostrar(Number(b.dataset.voltar)));
// Um botão só: guardar a credencial e avançar são o mesmo gesto.
// Salvar e depois clicar em continuar seria pedir duas confirmações
// para uma decisão só.
$('#ir-1').onclick = async () => {
  const digitada = $('#key').value.trim();

  try {
    // Sem campo preenchido, avança com o que já estava gravado —
    // quem volta para trocar o modelo não precisa digitar a chave
    // de novo.
    if (digitada || $('#model').value.trim()) {
      pintarEstado(await api('/api/key', {
        key: digitada, model: $('#model').value }));
      $('#key').value = '';
    }

    if ($('#ir-1').dataset.semChave) {
      $('#key-estado').textContent = 'A credential is required.';
      return;
    }

    feitos.add(0);
    mostrar(1);

  } catch (e) { $('#key-estado').textContent = e.message; }
};

function pintarEstado(e) {
  $('#repo').textContent = e.repository;
  // Marcador da versão servida. Existe porque o servidor carrega o
  // código na subida e não recarrega: uma aba antiga contra um
  // servidor novo produz sintomas que não estão em nenhum dos dois.
  $('#build').textContent = 'build ' + e.build;
  $('#key-estado').textContent =
    e.key ? 'credential ' + e.key : 'no credential yet';

  const opcao = m =>
    `<option value="${m.id}"${m.id === e.model ? ' selected' : ''}>` +
    `${m.id}</option>`;

  const grupo = (rotulo, lista) => lista.length
    ? `<optgroup label="${rotulo}">${lista.map(opcao).join('')}</optgroup>`
    : '';

  $('#model').innerHTML =
    grupo('Paid', e.models.filter(m => m.paid)) +
    grupo('Free — shared quota, expect 429',
          e.models.filter(m => !m.paid));

  if (e.key) delete $('#ir-1').dataset.semChave;
  else $('#ir-1').dataset.semChave = '1';
}

function bolha(texto, quem) {
  const d = document.createElement('div');
  d.className = 'msg ' + quem;
  d.textContent = texto;
  $('#conversa').append(d);
}

async function conversar(texto, botao, ecoar) {
  $('#chat-erro').textContent = '';
  // O texto da primeira mensagem não é ecoado: ele é a soma dos
  // quatro campos, que continuam na tela logo acima. Repeti-lo
  // empurraria a resposta do agente para fora da vista.
  if (ecoar) bolha(texto, 'user');
  botao.disabled = true;
  try {
    const { reply } = await api('/api/chat', { message: texto });
    bolha(reply, 'bot');
    $('#seguir').hidden = false;
    // O YAML gerado é gravado direto. Revisar num textarea do
    // navegador é pior do que revisar no editor: o arquivo fica
    // versionado, e o diff do git mostra o que mudou.
    const bloco = reply.match(/```(?:ya?ml)?\\n([\\s\\S]*?)```/);

    if (bloco) {
      const { written } = await api('/api/spec', { yaml: bloco[1].trim() });
      bolha('Declaration written to ' + written, 'bot');
      // Só avança quando o agente fechou uma declaração. Se ele
      // pediu esclarecimento, a etapa continua aberta — avançar
      // aqui deixaria a entrevista pela metade.
      feitos.add(1);
      mostrar(2);
    }
  } catch (e) { $('#chat-erro').textContent = e.message; }
  botao.disabled = false;
}

$('#enviar').onclick = () => {
  // Os quatro campos viram uma mensagem só, rotulada. O agente
  // precisa saber qual resposta é de qual assunto, e campo vazio é
  // informação: aquela tecnologia pode não ter equivalente.
  const partes = [
    ['Discovery',     $('#inventario').value.trim()],
    ['Composition',   $('#composicao').value.trim()],
    ['Routing',       $('#roteamento').value.trim()],
    ['Communication', $('#comunicacao').value.trim()],
  ].filter(([, v]) => v);

  if (!partes.length) {
    $('#chat-erro').textContent = 'Fill in at least one field.';
    return;
  }

  conversar(
    partes.map(([k, v]) => `## ${k}\\n${v}`).join('\\n\\n'),
    $('#enviar'),
    false
  );
};

$('#responder').onclick = () => {
  const texto = $('#mensagem').value.trim();
  if (!texto) return;
  $('#mensagem').value = '';
  conversar(texto, $('#responder'), true);
};

$('#rodar').onclick = async () => {
  $('#analise-estado').textContent = 'analysing…';
  $('#rodar').disabled = true;
  try {
    const r = await api('/api/analyze', {});
    const linhas = [
      ['extractor', r.extractor],
      ['micro frontends', r.microfrontends.length],
      ['screens', r.screens],
      ['fragments', r.fragments],
      ['fragment imports', r.fragment_imports],
      ['navigations', r.navigations],
      ['communications', r.communications],
      ['external calls', r.api_calls],
      ['global state reads', r.state_accesses],
    ];
    $('#resultado').innerHTML =
      '<table>' + linhas.map(([a,b]) =>
        `<tr><td>${a}</td><td>${b}</td></tr>`).join('') + '</table>' +
      (r.detections.length
        ? '<p class="nota" style="margin-top:14px">' +
          r.detections.length + ' occurrence(s): ' +
          [...new Set(r.detections.map(d=>d.rule))].join(', ') + '</p>'
        : '<p class="nota" style="margin-top:14px">no anti-patterns</p>');
    $('#resultado').hidden = false;
    $('#analise-estado').textContent = '';
    feitos.add(2); mostrar(2);
  } catch (e) { $('#analise-estado').textContent = e.message; }
  $('#rodar').disabled = false;
};

api('/api/state').then(e => { pintarEstado(e); mostrar(0); });
</script>
</body>
</html>
"""


BUILD = _build()
