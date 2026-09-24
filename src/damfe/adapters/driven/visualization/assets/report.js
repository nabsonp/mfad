// Interação do relatório.
//
// O SVG chega pronto do gerador: posições, curvas e rótulos foram
// calculados em Python. Este script só transforma o que já está na
// página — alterna classes, move o viewBox e preenche o painel a
// partir do JSON embutido. Sem ele a página continua mostrando a
// arquitetura; perde a exploração, não o conteúdo.

(function () {
  "use strict";

  var DATA = JSON.parse(document.getElementById("damfe-data").textContent);
  var RELATIONS = ["mount", "fragment_import", "navigation",
                   "communication", "shared_endpoint"];

  var svg = document.querySelector("#stage svg");
  var stage = document.getElementById("stage");
  var side = document.getElementById("side");
  var banner = document.getElementById("focus-banner");
  var bannerText = document.getElementById("focus-text");

  var state = {
    perspective: "all",
    search: "",
    onlyFlagged: false,
    selection: null,
    focus: null
  };

  var byId = {};
  DATA.microfrontends.forEach(function (item) { byId[item.id] = item; });

  var flagged = {};
  var detectionsOf = {};
  DATA.detections.forEach(function (detection) {
    (detection.subjects || []).forEach(function (subject) {
      flagged[subject] = true;
      (detectionsOf[subject] = detectionsOf[subject] || []).push(detection);
    });
  });

  // ------------------------------------------------------------ render

  function apply() {
    var term = state.search.trim().toLowerCase();

    document.querySelectorAll(".node").forEach(function (node) {
      var id = node.dataset.id;
      var visible = true;

      if (term && id.toLowerCase().indexOf(term) === -1) visible = false;
      if (state.onlyFlagged && !flagged[id]) visible = false;

      node.classList.toggle("hidden", !visible);
      node.classList.toggle("selected", state.selection === id);

      var dimmed = state.focus && state.focus.nodes.indexOf(id) === -1;
      node.classList.toggle("dim", !!dimmed);
      node.classList.toggle(
        "highlight",
        !!(state.focus && !dimmed)
      );
    });

    document.querySelectorAll(".edge-group").forEach(function (group) {
      var relation = group.dataset.relation;
      var source = group.dataset.source;
      var target = group.dataset.target;

      var visible = state.perspective === "all" ||
                    state.perspective === relation;

      if (visible && term) {
        visible = source.toLowerCase().indexOf(term) !== -1 ||
                  target.toLowerCase().indexOf(term) !== -1;
      }

      if (visible && state.onlyFlagged) {
        visible = flagged[source] && flagged[target];
      }

      if (visible && document.querySelector(
            '.node[data-id="' + cssEscape(source) + '"]'
          ).classList.contains("hidden")) visible = false;

      group.classList.toggle("hidden", !visible);

      var inFocus = state.focus &&
                    state.focus.edges.indexOf(group.dataset.edge) !== -1;

      group.classList.toggle("dim", !!(state.focus && !inFocus));
      group.querySelector(".edge").classList.toggle(
        "highlight", !!inFocus
      );
    });

    banner.classList.toggle("on", !!state.focus);
  }

  function cssEscape(value) {
    return value.replace(/["\\]/g, "\\$&");
  }

  // -------------------------------------------------------- zoom e pan

  var view = svg.getAttribute("viewBox").split(" ").map(Number);
  var home = view.slice();

  function setView(next) {
    view = next;
    svg.setAttribute("viewBox", next.join(" "));
  }

  svg.addEventListener("wheel", function (event) {
    event.preventDefault();
    var factor = event.deltaY > 0 ? 1.12 : 0.89;
    var box = svg.getBoundingClientRect();
    var rx = (event.clientX - box.left) / box.width;
    var ry = (event.clientY - box.top) / box.height;
    var w = view[2] * factor;
    var h = view[3] * factor;
    setView([
      view[0] + (view[2] - w) * rx,
      view[1] + (view[3] - h) * ry,
      w, h
    ]);
  }, { passive: false });

  var dragging = null;
  svg.addEventListener("pointerdown", function (event) {
    if (event.target.closest(".node, .edge-group")) return;
    dragging = { x: event.clientX, y: event.clientY, view: view.slice() };
    svg.setPointerCapture(event.pointerId);
  });
  svg.addEventListener("pointermove", function (event) {
    if (!dragging) return;
    var box = svg.getBoundingClientRect();
    var dx = (event.clientX - dragging.x) / box.width * dragging.view[2];
    var dy = (event.clientY - dragging.y) / box.height * dragging.view[3];
    setView([
      dragging.view[0] - dx, dragging.view[1] - dy,
      dragging.view[2], dragging.view[3]
    ]);
  });
  svg.addEventListener("pointerup", function () { dragging = null; });
  svg.addEventListener("pointercancel", function () { dragging = null; });

  // ----------------------------------------------------------- painel

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function snippet(edge) {
    if (!edge.code) return "";
    return '<pre class="snippet"><span class="ln">' +
           escapeHtml(edge.line) + "</span>  " +
           escapeHtml(edge.code) + "</pre>";
  }

  function showMicroFrontend(id) {
    var item = byId[id];
    if (!item) return;

    state.selection = id;
    state.focus = null;

    var outgoing = DATA.edges.filter(function (e) { return e.source === id; });
    var incoming = DATA.edges.filter(function (e) { return e.target === id; });

    var deps = "";
    dedupe(outgoing).forEach(function (e) {
      deps += '<div class="dep"><span class="dir">→</span>' +
              escapeHtml(shortOf(e.target)) +
              '<span class="kind">' + label(e.relation) + "</span></div>";
    });
    dedupe(incoming).forEach(function (e) {
      deps += '<div class="dep"><span class="dir">←</span>' +
              escapeHtml(shortOf(e.source)) +
              '<span class="kind">' + label(e.relation) + "</span></div>";
    });

    var screens = item.screens.map(function (s) {
      return "<li>" + escapeHtml(s.component) +
             (s.route ? " <code>" + escapeHtml(s.route) + "</code>" : "") +
             "</li>";
    }).join("");

    var fragments = item.fragments.map(function (f) {
      return "<li>" + escapeHtml(f.name) + "</li>";
    }).join("");

    var apis = DATA.api_calls.filter(function (c) {
      return c.microfrontend === id;
    });
    var seen = {};
    var endpoints = apis.filter(function (c) {
      var key = c.method + c.path;
      if (seen[key]) return false;
      seen[key] = true;
      return true;
    }).map(function (c) {
      return "<li><span class=\"mono\">" + escapeHtml(c.method) + "</span> " +
             "<code>" + escapeHtml(c.path) + "</code></li>";
    }).join("");

    var found = (detectionsOf[id] || []).map(function (d) {
      return "<li>" + escapeHtml(d.rule) +
             (d.dimension ? " · " + escapeHtml(d.dimension) : "") + "</li>";
    }).join("");

    side.innerHTML =
      '<div class="body">' +
      "<h3>" + escapeHtml(item.id) + "</h3>" +
      (item.role === "shell"
        ? '<span class="badge shell">orquestrador</span>'
        : '<span class="badge">micro frontend</span>') +
      '<div class="summary">' +
        cell(item.screens.length, "telas") +
        cell(item.fragments.length, "fragmentos") +
        cell(item.degree.in, "entradas") +
        cell(item.degree.out, "saídas") +
        cell(item.detections, "anti-padrões") +
      "</div>" +
      '<div class="group"><h4>Tamanho</h4>' +
        item.size.code_lines.toLocaleString("pt-BR") +
        " linhas de código · " + item.size.files + " arquivos" +
        " <span class=\"mono\">(" +
        item.size.lines.toLocaleString("pt-BR") + " físicas)</span></div>" +
      '<div class="group"><h4>Rotas</h4><code>' +
        escapeHtml(item.routes.join(", ") || "—") + "</code></div>" +
      '<div class="group"><h4>Telas · ' + item.screens.length + "</h4><ul>" +
        (screens || "<li>—</li>") + "</ul></div>" +
      '<div class="group"><h4>Fragmentos expostos · ' +
        item.fragments.length + "</h4><ul>" +
        (fragments || "<li>—</li>") + "</ul></div>" +
      '<div class="group"><h4>Serviços externos · ' + apis.length +
        "</h4><ul>" + (endpoints || "<li>—</li>") + "</ul></div>" +
      '<div class="group"><h4>Dependências</h4>' +
        (deps || '<p class="empty">nenhuma</p>') + "</div>" +
      '<div class="group"><h4>Anti-padrões</h4><ul>' +
        (found || '<li class="empty">nenhum</li>') + "</ul></div>" +
      '<div class="group"><h4>Origem</h4><code>' +
        escapeHtml(item.entrypoint || item.directory || "—") +
        "</code></div>" +
      "</div>";

    apply();
  }

  function showEdge(edgeId) {
    var items = DATA.edges.filter(function (e) { return e.edge === edgeId; });
    if (!items.length) return;

    state.selection = null;
    var first = items[0];

    // Uma aresta no desenho é a abstração de várias ocorrências no
    // código. O painel desdobra: o que passa por ela, quantas vezes,
    // e em que linha.
    var used = [];
    var seen = {};
    items.forEach(function (e) {
      if (e.label && !seen[e.label]) { seen[e.label] = true; used.push(e.label); }
    });

    var usedList = used.map(function (label) {
      return "<li><code>" + escapeHtml(label) + "</code></li>";
    }).join("");

    var occurrences = items.filter(function (e) { return e.file; })
      .map(function (e) {
        var renders = (e.renders || []).map(function (r) {
          return "<li>instanciado em <code>" + escapeHtml(r.file) + ":" +
                 r.line + "</code>" +
                 (r.screens && r.screens.length
                   ? " · aparece em " + escapeHtml(r.screens.join(", "))
                   : " · nenhuma tela alcança") +
                 (r.props && r.props.length
                   ? " · props: " + escapeHtml(r.props.join(", "))
                   : "") + "</li>";
        }).join("");
        return "<div class=\"group\"><h4>" +
               escapeHtml(e.file) + ":" + e.line + "</h4>" +
               (e.detail ? '<p class="mono">' + escapeHtml(e.detail) + "</p>" : "") +
               snippet(e) +
               (renders ? "<ul>" + renders + "</ul>" : "") +
               "</div>";
      }).join("");

    side.innerHTML =
      '<div class="body">' +
      "<h3>" + labelTitle(first.relation) + "</h3>" +
      '<div class="flow">' + escapeHtml(shortOf(first.source)) +
        "<br>↓<br>" + escapeHtml(shortOf(first.target)) + "</div>" +
      '<div class="group"><h4>' + usedHeading(first.relation) + "</h4><ul>" +
        (usedList || "<li>—</li>") + "</ul></div>" +
      '<div class="group"><h4>' + items.length + " ocorrência" +
        (items.length > 1 ? "s" : "") + "</h4></div>" +
      occurrences +
      "</div>";

    apply();
  }

  function labelTitle(relation) {
    return { mount: "Montagem", fragment_import: "Composição",
             navigation: "Navegação", communication: "Comunicação",
             shared_endpoint: "Backend compartilhado" }[relation] || relation;
  }

  function usedHeading(relation) {
    return { mount: "Aplicações montadas",
             fragment_import: "Fragmentos utilizados",
             navigation: "Rotas de destino",
             communication: "Canais",
             shared_endpoint: "Endpoints em comum" }[relation] || "Itens";
  }

  function cell(value, label) {
    return "<div><strong>" + value + "</strong><span>" +
           label + "</span></div>";
  }

  function dedupe(edges) {
    var seen = {};
    return edges.filter(function (e) {
      var key = e.source + e.target + e.relation;
      if (seen[key]) return false;
      seen[key] = true;
      return true;
    });
  }

  function shortOf(id) {
    return (byId[id] && byId[id].short) || id;
  }

  function label(relation) {
    return { mount: "montagem", fragment_import: "composição",
             navigation: "navegação", communication: "comunicação",
             shared_endpoint: "backend compartilhado" }[relation] ||
           relation;
  }

  // ------------------------------------------------------------- foco

  function focusOn(index) {
    var detection = DATA.detections[index];
    if (!detection) return;

    state.focus = {
      nodes: detection.subjects || [],
      edges: detection.edges || []
    };
    state.perspective = "all";
    state.onlyFlagged = false;
    state.search = "";

    document.querySelectorAll(".tab").forEach(function (tab) {
      tab.setAttribute("aria-pressed", tab.dataset.perspective === "all");
    });
    document.getElementById("search").value = "";
    document.getElementById("only-flagged").checked = false;

    bannerText.textContent = detection.rule + " — " + detection.message;

    apply();
    stage.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function clearFocus() {
    state.focus = null;
    apply();
  }

  // ---------------------------------------------------------- eventos

  svg.addEventListener("click", function (event) {
    var node = event.target.closest(".node");
    if (node) { showMicroFrontend(node.dataset.id); return; }

    var edge = event.target.closest(".edge-group");
    if (edge) { showEdge(edge.dataset.edge); }
  });

  document.querySelectorAll(".tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      state.perspective = tab.dataset.perspective;
      document.querySelectorAll(".tab").forEach(function (other) {
        other.setAttribute("aria-pressed", other === tab);
      });
      apply();
    });
  });

  document.getElementById("search").addEventListener("input", function (e) {
    state.search = e.target.value;
    apply();
  });

  document.getElementById("only-flagged")
    .addEventListener("change", function (e) {
      state.onlyFlagged = e.target.checked;
      apply();
    });

  document.getElementById("reset-view").addEventListener("click", function () {
    setView(home.slice());
    clearFocus();
  });

  document.getElementById("clear-focus")
    .addEventListener("click", clearFocus);

  document.querySelectorAll("[data-focus]").forEach(function (button) {
    button.addEventListener("click", function () {
      focusOn(Number(button.dataset.focus));
    });
  });

  document.querySelectorAll("[data-select]").forEach(function (row) {
    row.addEventListener("click", function () {
      showMicroFrontend(row.dataset.select);
      stage.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  });

  apply();
})();
