// Report interaction.
//
// The SVGs arrive ready from the generator: positions, curves and labels were
// computed in Python, one drawing per view, all in view on the
// dashboard. This script only transforms what is already on the page:
// it highlights neighbors in every graph, adjusts the zoom of each one and
// fills the panel from the embedded JSON. Without it the page
// still shows the graphs; it loses the exploration, not the content.

(function () {
  "use strict";

  var DATA = JSON.parse(document.getElementById("mfad-data").textContent);

  var stage = document.getElementById("stage");
  // The sidebar and its body, which each `show…` fills.
  var drawer = document.getElementById("side");
  var side = document.getElementById("side-body");
  var banner = document.getElementById("focus-banner");
  var bannerText = document.getElementById("focus-text");

  var state = {
    page: "home",
    variant: {},
    view: null,
    search: "",
    onlyFlagged: false,
    pinned: null,
    focus: null,
    zoom: {}
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

  // ------------------------------------------------------------ language
  //
  // Every text comes from `texts.json`, embedded in the page. The HTML arrives
  // in English with each text marked by its key (`data-t`) and its
  // values (`data-a`); switching language rebuilds the sentences from
  // them. The panel is built here and uses the same keys.

  var TEXTS = JSON.parse(document.getElementById("mfad-texts").textContent);
  var LANGUAGES = ["pt", "en"];
  // The language the HTML arrives in: the same as `i18n.DEFAULT`.
  var DEFAULT = "en";
  var language = DEFAULT;

  // The choice stays in the reader's browser. Without storage (private
  // tab, preview), it falls back to English, and the page works the same.
  try {
    var saved = localStorage.getItem("mfad-language");
    if (LANGUAGES.indexOf(saved) !== -1) language = saved;
  } catch (error) { /* no storage */ }

  // `lang=pt` in the address beats the stored choice: a shared link
  // opens in the language of whoever sent it.
  var linked = (location.hash.match(/lang=(\w+)/) || [])[1];
  if (LANGUAGES.indexOf(linked) !== -1) language = linked;

  function t(key, args) {
    if (key && typeof key === "object") { args = key.args; key = key.key; }
    var entry = TEXTS[key];
    if (!entry) return key;
    var values = {};
    Object.keys(args || {}).forEach(function (name) {
      var value = args[name];
      values[name] = value && typeof value === "object" && value.key ? t(value) : value;
    });
    var template = entry[language] || entry[DEFAULT];
    if (typeof template === "object") {
      template = template[values[entry.plural || "n"] === 1 ? "one" : "other"];
    }
    return template.replace(/\{(\w+)\}/g, function (whole, name) {
      return name in values ? values[name] : whole;
    });
  }

  function number(value) {
    return Number(value).toLocaleString(language === "pt" ? "pt-BR" : "en");
  }

  // What the arrow means, with the real names. The same text
  // as the legend, so the panel leaves no doubt about who is who.
  function meaning(relation, a, b, screens) {
    return t((screens ? "screen_direction." : "direction.") + relation, { a: a, b: b });
  }

  function relationName(relation) { return t("relation." + relation); }

  // Occurrence text: a text reference or a code snippet.
  function detailText(detail) {
    return detail && typeof detail === "object" ? t(detail) : detail;
  }

  function translate(root) {
    root.querySelectorAll("[data-t]").forEach(function (element) {
      var text = t(element.dataset.t, element.dataset.a ? JSON.parse(element.dataset.a) : {});
      if (element.dataset.tAttr) element.setAttribute(element.dataset.tAttr, text);
      else if (element.dataset.tHtml) element.innerHTML = text;
      else element.textContent = text;
    });
  }

  // The open panel redraws itself in the new language.
  var redraw = null;

  function setLanguage(next) {
    language = next;
    try { localStorage.setItem("mfad-language", next); } catch (error) { /* no storage */ }
    document.documentElement.lang = next === "pt" ? "pt-BR" : "en";
    translate(document);
    // The slices kept in <template> and the drawing swapped for a
    // slice too: otherwise they would come back in the old language.
    document.querySelectorAll("template").forEach(function (template) {
      translate(template.content);
    });
    Object.keys(originals).forEach(function (id) { translate(originals[id]); });
    document.querySelectorAll("[data-lang]").forEach(function (button) {
      button.setAttribute("aria-pressed", button.dataset.lang === next);
    });
    remember();
    if (redraw) redraw();
    if (state.focusIndex != null) bannerText.textContent = bannerOf(state.focusIndex);
  }

  // ------------------------------------------------------------ views
  //
  // All graphs are in view, each in its own card. `state.view`
  // is the last one visited (through a shortcut, a detection or the
  // address), which the card marks and the link keeps.

  function views() { return document.querySelectorAll(".view"); }

  function viewOf(id) {
    return document.querySelector('.view[data-view="' + id + '"]');
  }

  function current() { return viewOf(state.view); }

  function svgOf(view) { return view && view.querySelector("svg"); }

  function show(viewId) {
    if (!viewOf(viewId)) return;
    state.view = viewId;
    remember();
    views().forEach(function (view) {
      view.classList.toggle("active", view.dataset.view === viewId);
    });
  }

  // Brings the card of the chosen view to the middle of the screen.
  function reveal() {
    var view = current();
    if (view) view.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  // The address keeps where one is (tab, view, slice and language)
  // so a shared link opens at the same place.
  function remember() {
    if (!history.replaceState) return;
    var parts = [];
    if (state.page !== "home") parts.push("page=" + state.page);
    else if (state.view) {
      parts.push("view=" + state.view);
      if (state.variant[state.view]) parts.push("mfe=" + encodeURIComponent(state.variant[state.view]));
    }
    if (language !== DEFAULT) parts.push("lang=" + language);
    history.replaceState(null, "", parts.length ? "#" + parts.join("&") : location.pathname + location.search);
  }

  // ------------------------------------------------------------ pages
  //
  // The header numbers are the tabs: the first box is the map, and
  // each number opens the table it adds up.

  function showPage(page) {
    if (!document.querySelector('.page[data-page="' + page + '"]')) return;
    state.page = page;
    document.querySelectorAll(".page").forEach(function (element) {
      element.classList.toggle("hidden", element.dataset.page !== page);
    });
    document.querySelectorAll(".metric[data-page]").forEach(function (tab) {
      tab.setAttribute("aria-selected", tab.dataset.page === page);
    });
    // The hidden dashboard has no width: the zoom computed
    // while it was hidden is not valid, and is redone on return.
    if (page === "home" && state.hiddenFit) {
      state.hiddenFit = false;
      fitAll();
      apply();
    }
    remember();
  }

  document.querySelectorAll(".metric[data-page]").forEach(function (tab) {
    tab.addEventListener("click", function () {
      showPage(tab.dataset.page);
      window.scrollTo({ top: 0 });
    });
  });

  // Filtering, sorting and opening of rows. Each item is two
  // rows (the summary and the detail) that move together: the filter looks at
  // the text of both, and sorting moves the pair.
  function pairs(tbody) {
    var found = [];
    Array.prototype.forEach.call(tbody.rows, function (row) {
      if (row.classList.contains("item")) found.push([row, row.nextElementSibling]);
    });
    return found;
  }

  document.querySelectorAll(".table-tools").forEach(function (tools) {
    var input = tools.querySelector(".table-filter");
    var count = tools.querySelector(".table-count");
    var tbody = tools.nextElementSibling.querySelector("tbody");
    var items = pairs(tbody);

    input.addEventListener("input", function () {
      var term = input.value.trim().toLowerCase();
      var shown = 0;
      items.forEach(function (pair) {
        var text = (pair[0].textContent + " " + pair[1].textContent).toLowerCase();
        var visible = !term || text.indexOf(term) !== -1;
        pair[0].classList.toggle("hidden", !visible);
        if (!visible) pair[1].classList.add("hidden");
        else if (pair[0].classList.contains("open")) pair[1].classList.remove("hidden");
        if (visible) shown += 1;
      });
      count.dataset.a = JSON.stringify({ n: shown, total: items.length });
      count.textContent = t("table.count", { n: shown, total: items.length });
    });
  });

  document.querySelectorAll("table.data th[data-sort]").forEach(function (header) {
    header.addEventListener("click", function () {
      var table = header.closest("table");
      var tbody = table.tBodies[0];
      var index = Array.prototype.indexOf.call(header.parentNode.children, header);
      var numeric = header.dataset.sort === "num";
      var ascending = header.getAttribute("aria-sort") !== "ascending";
      table.querySelectorAll("th").forEach(function (other) { other.removeAttribute("aria-sort"); });
      header.setAttribute("aria-sort", ascending ? "ascending" : "descending");
      var items = pairs(tbody);
      items.sort(function (a, b) {
        var x = a[0].cells[index].textContent.trim();
        var y = b[0].cells[index].textContent.trim();
        var order = numeric ? (Number(x) || 0) - (Number(y) || 0)
                            : x.localeCompare(y, language === "pt" ? "pt-BR" : "en", { numeric: true });
        return ascending ? order : -order;
      });
      items.forEach(function (pair) { tbody.appendChild(pair[0]); tbody.appendChild(pair[1]); });
    });
  });

  function toggle(row) {
    var open = !row.classList.contains("open");
    row.classList.toggle("open", open);
    row.nextElementSibling.classList.toggle("hidden", !open);
  }

  // Opens the tab with the key's rows open and in view; with `only`,
  // shows only them, closed: the screens of a micro frontend, not
  // all open at once. Typing in the filter shows everything again.
  function openRow(page, key, only) {
    showPage(page);
    var element = document.querySelector('.page[data-page="' + page + '"]');
    var input = element.querySelector(".table-filter");
    if (input) {
      input.value = "";
      input.dispatchEvent(new Event("input"));
    }
    var items = element.querySelectorAll("tr.item");
    var rows = Array.prototype.filter.call(items, function (row) {
      return (row.dataset.key || "").split(" ").indexOf(key) !== -1;
    });
    if (only) {
      Array.prototype.forEach.call(items, function (row) {
        var hide = rows.indexOf(row) === -1;
        row.classList.toggle("hidden", hide);
        if (hide) row.nextElementSibling.classList.add("hidden");
      });
      var count = element.querySelector(".table-count");
      count.dataset.a = JSON.stringify({ n: rows.length, total: items.length });
      count.textContent = t("table.count", { n: rows.length, total: items.length });
      window.scrollTo({ top: 0 });
      return;
    }
    rows.forEach(function (row) {
      if (!row.classList.contains("open")) toggle(row);
      row.classList.add("flash");
      setTimeout(function () { row.classList.remove("flash"); }, 1600);
    });
    if (rows.length) rows[0].scrollIntoView({ behavior: "smooth", block: "center" });
  }

  document.querySelectorAll("table.data tbody").forEach(function (tbody) {
    tbody.addEventListener("click", function (event) {
      var go = event.target.closest("button.go");
      // The detection button has its own listener (`data-focus`).
      if (go) { if (go.dataset.goKind) goTo(go.dataset); return; }
      var row = event.target.closest("tr.item");
      // Selecting text in the detail does not close the row.
      if (row) toggle(row);
    });
    tbody.addEventListener("keydown", function (event) {
      var row = event.target.closest("tr.item");
      if (row && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); toggle(row); }
    });
  });

  // The row's shortcut to the map: the selected micro frontend, the
  // relation with its panel open, the slice, the endpoint or the screen.
  function goTo(data) {
    showPage("home");
    var kind = data.goKind;
    var target = data.goTarget;
    var view = data.goView;
    if (kind === "mfe") {
      show("overview");
      showMicroFrontend(target);
      pin(target);
    } else if (kind === "edge") {
      show(viewOf(view) ? view : "overview");
      showEdge([target]);
      pin(data.goSource);
    } else if (kind === "slot") {
      show(view);
      showSlot(target, view === "state" ? "state" : "backend");
      pin(target);
    } else if (kind === "screen") {
      show("screens");
      showScreen(target);
      pin(target);
    }
    restart();
    openSide();
    reveal();
  }

  // -------------------------------------------------------------- zoom
  //
  // The drawing is shown at natural size and scrolls inside the window:
  // legible text is worth more than fitting everything at once. Zoom changes the
  // SVG size; dragging the background scrolls.

  function applyZoom(view) {
    var svg = svgOf(view);
    if (!svg) return;
    var z = state.zoom[view.dataset.view] || 1;
    svg.setAttribute("width", Math.round(svg.dataset.width * z));
    svg.setAttribute("height", Math.round(svg.dataset.height * z));
  }

  // A graph opens fully in view in the card, enlarged if small; a long
  // list (state, backend, screens) opens at full width and scrolls vertically.
  function fit(view) {
    var svg = svgOf(view);
    if (!svg) return;
    var viewport = view.querySelector(".viewport");
    // A hidden card (another tab open) has no size: it is left for later.
    if (!viewport.clientWidth) { state.hiddenFit = true; return; }
    var width = Number(svg.dataset.width);
    var height = Number(svg.dataset.height);
    var available = viewport.clientWidth - 4;
    var tall = viewport.clientHeight - 8;
    var contain = svg.dataset.fit === "contain";
    var z = contain
      ? Math.min(available / width, tall / height, 1.3)
      : Math.min(available / width, 1);
    // In the card, the whole graph fits, to see its shape; when enlarged,
    // below the minimum the text stops being legible, and scrolling is better.
    var expanded = view.classList.contains("expanded");
    state.zoom[view.dataset.view] = Math.max(z, contain ? (expanded ? 0.4 : 0.1) : 0.6);
    applyZoom(view);
    // Whatever does not fit opens from the middle, not from the corner.
    if (contain) {
      viewport.scrollLeft = (viewport.scrollWidth - viewport.clientWidth) / 2;
      viewport.scrollTop = (viewport.scrollHeight - viewport.clientHeight) / 2;
    }
  }

  function fitAll() { views().forEach(fit); }

  function zoomBy(view, factor) {
    var id = view.dataset.view;
    var z = (state.zoom[id] || 1) * factor;
    state.zoom[id] = Math.min(3, Math.max(0.2, z));
    applyZoom(view);
  }

  // Enlarging makes the card taller; the graph adjusts to the new space.
  function expand(view) {
    var on = !view.classList.contains("expanded");
    view.classList.toggle("expanded", on);
    var button = view.querySelector('[data-zoom="expand"]');
    button.dataset.t = on ? "map.shrink" : "map.expand";
    button.textContent = t(button.dataset.t);
    fit(view);
    view.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  stage.addEventListener("click", function (event) {
    var button = event.target.closest("[data-zoom]");
    if (!button) return;
    var view = button.closest(".view");
    var action = button.dataset.zoom;
    if (action === "in") zoomBy(view, 1.2);
    else if (action === "out") zoomBy(view, 1 / 1.2);
    else if (action === "fit") fit(view);
    else if (action === "expand") expand(view);
  });

  document.querySelectorAll(".viewport").forEach(function (viewport) {
    viewport.addEventListener("wheel", function (event) {
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      zoomBy(viewport.closest(".view"), event.deltaY > 0 ? 1 / 1.1 : 1.1);
    }, { passive: false });

    var drag = null;
    viewport.addEventListener("pointerdown", function (event) {
      if (event.target.closest(".node, .slot, .screen-node, .edge-group, .cluster")) return;
      drag = { x: event.clientX, y: event.clientY,
               left: viewport.scrollLeft, top: viewport.scrollTop };
      viewport.setPointerCapture(event.pointerId);
      viewport.classList.add("dragging");
    });
    viewport.addEventListener("pointermove", function (event) {
      if (!drag) return;
      viewport.scrollLeft = drag.left - (event.clientX - drag.x);
      viewport.scrollTop = drag.top - (event.clientY - drag.y);
    });
    function stop() { drag = null; viewport.classList.remove("dragging"); }
    viewport.addEventListener("pointerup", stop);
    viewport.addEventListener("pointercancel", stop);
  });

  // ------------------------------------------------------- highlight
  //
  // Each element of the drawing has a key: the micro frontend
  // (`data-id`), the slice or endpoint (`data-slot`), the screen
  // (`data-screen`). Edges state the keys of their two ends.

  function keyOf(element) {
    return element.dataset.id || element.dataset.slot || element.dataset.screen;
  }

  function mfeOf(element) {
    return element.dataset.mfe || element.dataset.id || null;
  }

  function touches(edge, keys) {
    if (keys[edge.dataset.source] || keys[edge.dataset.target]) return true;
    var mfes = (edge.dataset.mfes || "").split(" ");
    return mfes.some(function (id) { return keys[id]; });
  }

  // Lights up the edges that touch the keys and their ends; dims the
  // rest. Without keys, everything goes back to normal.
  //
  // On a detection focus (`edgeIds`), what counts is the edge it cites
  // or the one linking two involved parties. Slices and endpoints are not micro
  // frontends: when the detection does not name one, any slice or
  // endpoint of an involved party counts.
  function highlight(view, keys, edgeIds) {
    keys = keys || {};
    var names = Object.keys(keys);
    var active = names.length > 0 || !!edgeIds;
    var namesSlot = names.some(function (k) { return !byId[k]; });
    var lit = {};

    view.querySelectorAll(".edge-group").forEach(function (edge) {
      var source = edge.dataset.source;
      var target = edge.dataset.target;
      var on = false;

      if (edgeIds) {
        on = (edge.dataset.edges || "").split(" ").some(function (id) { return edgeIds[id]; }) ||
             (keys[source] && keys[target]) ||
             (keys[source] && !byId[target] && !namesSlot);
      } else if (active) {
        on = touches(edge, keys);
      }

      edge.classList.toggle("dim", active && !on);
      edge.classList.toggle("lit", active && on);

      if (on) {
        lit[source] = true;
        lit[target] = true;
        (edge.dataset.mfes || "").split(" ").forEach(function (id) { if (id) lit[id] = true; });
      }
    });

    view.querySelectorAll(".node, .slot, .screen-node, .cluster").forEach(function (node) {
      var key = keyOf(node);
      var mine = keys[key] || keys[mfeOf(node)] || lit[key];
      node.classList.toggle("dim", active && !mine);
      node.classList.toggle("lit", active && !!mine);
    });
  }

  // The filters and the highlight apply to all graphs: the same micro
  // frontend lit in each of them.
  function apply() {
    views().forEach(applyTo);
    banner.classList.toggle("on", !!state.focus);
  }

  function applyTo(view) {
    var term = state.search.trim().toLowerCase();

    // "Only with anti-pattern" filter: hides micro frontends without
    // a detection and the edges that depended on them.
    view.querySelectorAll(".node").forEach(function (node) {
      node.classList.toggle("hidden", state.onlyFlagged && !flagged[node.dataset.id]);
    });
    view.querySelectorAll(".cluster").forEach(function (node) {
      node.classList.toggle("hidden", state.onlyFlagged && !flagged[node.dataset.id]);
    });
    view.querySelectorAll(".screen-node").forEach(function (node) {
      node.classList.toggle("hidden", state.onlyFlagged && !flagged[node.dataset.mfe]);
    });
    view.querySelectorAll(".edge-group").forEach(function (edge) {
      var hidden = false;
      if (state.onlyFlagged) {
        var mfes = (edge.dataset.mfes || (edge.dataset.source + " " + edge.dataset.target)).split(" ");
        hidden = mfes.some(function (id) { return byId[id] && !flagged[id]; });
      }
      edge.classList.toggle("hidden", hidden);
    });

    if (state.focus) {
      highlight(view, state.focus.nodes, state.focus.edges);
    } else if (state.pinned) {
      var keys = {}; keys[state.pinned] = true;
      highlight(view, keys, null);
    } else if (term) {
      var matched = {};
      view.querySelectorAll(".node, .slot, .screen-node, .cluster").forEach(function (node) {
        var key = keyOf(node) || "";
        var text = (key + " " + node.textContent).toLowerCase();
        if (text.indexOf(term) !== -1) matched[key] = true;
      });
      highlight(view, matched, null);
    } else {
      highlight(view, null, null);
    }

    view.querySelectorAll(".selected").forEach(function (node) {
      node.classList.remove("selected");
    });
    if (state.pinned) {
      view.querySelectorAll("[data-id], [data-slot], [data-screen]").forEach(function (node) {
        if (!node.classList.contains("edge-group") && keyOf(node) === state.pinned) {
          node.classList.add("selected");
        }
      });
    }
  }

  stage.addEventListener("mouseover", function (event) {
    if (state.pinned || state.focus || state.search) return;
    var node = event.target.closest(".node, .slot, .screen-node, .cluster");
    if (!node) return;
    var keys = {}; keys[keyOf(node)] = true;
    views().forEach(function (view) { highlight(view, keys, null); });
  });

  stage.addEventListener("mouseout", function (event) {
    if (state.pinned || state.focus || state.search) return;
    var node = event.target.closest(".node, .slot, .screen-node, .cluster");
    if (!node || (event.relatedTarget && node.contains(event.relatedTarget))) return;
    apply();
  });

  // ----------------------------------------------------------- panel

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function snippet(item) {
    if (!item.code) return "";
    return '<pre class="snippet"><span class="ln">' +
           escapeHtml(item.line) + "</span>  " +
           escapeHtml(item.code) + "</pre>";
  }

  function where(item) {
    if (!item.file) return "";
    return "<code>" + escapeHtml(item.file) + ":" + item.line + "</code>";
  }

  function shortOf(id) {
    if (byId[id]) return byId[id].short;
    var screen = DATA.screens[id];
    if (screen) return screen.name;
    return id;
  }

  function placeOf(id) {
    var screen = DATA.screens[id];
    if (screen) {
      return escapeHtml(screen.name) + ' <span class="muted">(' +
             escapeHtml(shortOf(screen.microfrontend)) + ")</span>";
    }
    return escapeHtml(shortOf(id)) + ' <span class="muted">(' + escapeHtml(t("screen.outside")) + ")</span>";
  }

  function nameOf(id) {
    var screen = DATA.screens[id];
    return screen ? screen.name : t("screen.outside_named", { name: shortOf(id) });
  }

  function cell(value, label) {
    return "<div><strong>" + value + "</strong><span>" + label + "</span></div>";
  }

  function group(title, inner) {
    return '<div class="group"><h4>' + title + "</h4>" + inner + "</div>";
  }

  // Sidebar links. `mfeLink` opens another micro frontend in the sidebar itself (with
  // the ← to go back); `out` leads to the tab that has the item, with its row
  // open, or, without a key, the table filtered by the term.
  function mfeLink(id) {
    return '<a href="#" data-mfe-link="' + escapeHtml(id) + '">' + escapeHtml(shortOf(id)) + "</a>";
  }

  // `only`: instead of opening the key's rows, shows only them.
  function out(page, key, only) {
    return ' <a href="#" class="out" data-page-link="' + page + '"' +
           ' data-row="' + escapeHtml(key) + '"' + (only ? ' data-only="1"' : "") +
           ' title="' + escapeHtml(t("side.open_table")) + '">↗</a>';
  }

  // The tab of each relation.
  var PAGE_OF = { composition: "fragments", navigation: "navigations",
                  communication: "communications", mount: "microfrontends" };

  function relationOut(relation, source, target) {
    if (relation === "mount") return out("microfrontends", target);
    return PAGE_OF[relation] ? out(PAGE_OF[relation], source + ">" + target) : "";
  }

  // The detection row that shows the slice: the global-state one.
  function sliceDetection(id) {
    var found = DATA.detections.filter(function (d) {
      return ((d.metadata || {}).slices || {})[id];
    })[0];
    return found ? out("detections", String(found.index)) : "";
  }

  function list(items, empty) {
    return items.length ? "<ul>" + items.join("") + "</ul>"
                        : '<p class="empty">' + (empty || "—") + "</p>";
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

  function showMicroFrontend(id) {
    var item = byId[id];
    if (!item) return;
    redraw = function () { showMicroFrontend(id); };

    var outgoing = DATA.edges.filter(function (e) { return e.source === id; });
    var incoming = DATA.edges.filter(function (e) { return e.target === id; });

    var deps = dedupe(outgoing).map(function (e) {
      return '<div class="dep"><span class="dir">→</span>' +
             (byId[e.target] ? mfeLink(e.target) : escapeHtml(shortOf(e.target))) +
             '<span class="kind">' + relationName(e.relation) +
             relationOut(e.relation, e.source, e.target) + "</span></div>";
    }).concat(dedupe(incoming).map(function (e) {
      return '<div class="dep"><span class="dir">←</span>' +
             (byId[e.source] ? mfeLink(e.source) : escapeHtml(shortOf(e.source))) +
             '<span class="kind">' + relationName(e.relation) +
             relationOut(e.relation, e.source, e.target) + "</span></div>";
    })).join("");

    var related = {};
    DATA.screen_edges.forEach(function (e) {
      [e.source, e.target].forEach(function (node) {
        var owner = DATA.screens[node] ? DATA.screens[node].microfrontend : node;
        if (owner === id) related[node] = true;
      });
    });

    var screens = item.screens.map(function (s) {
      var key = id + "#" + s.component;
      return "<li>" + (related[key]
        ? '<a href="#" data-screen-link="' + escapeHtml(key) + '">' + escapeHtml(s.component) + "</a>"
        : escapeHtml(s.component)) +
        (s.route ? " <code>" + escapeHtml(s.route) + "</code>" : "") +
        out("screens", key) + "</li>";
    });

    var fragments = item.fragments.map(function (f) {
      return "<li>" + escapeHtml(f.name) + out("fragments", id + "#" + f.name) + "</li>";
    });

    var seen = {};
    var endpoints = DATA.api_calls.filter(function (c) {
      if (c.microfrontend !== id) return false;
      var key = c.method + c.path;
      if (seen[key]) return false;
      seen[key] = true;
      return true;
    }).map(function (c) {
      return '<li><span class="mono">' + escapeHtml(c.method) + "</span> " +
             "<code>" + escapeHtml(c.path) + "</code>" + out("api_calls", c.path) + "</li>";
    });

    var slices = DATA.slices.filter(function (s) {
      return s.microfrontends.indexOf(id) !== -1;
    }).map(function (s) {
      var kinds = {};
      s.accesses.forEach(function (a) { if (a.microfrontend === id) kinds[a.access] = true; });
      return '<li><a href="#" data-slot-link="' + escapeHtml(s.id) + '">' +
             escapeHtml(s.path) + "</a> " +
             '<span class="muted">' + escapeHtml(s.library) + " · " +
             Object.keys(kinds).sort().map(function (k) {
               return t(k === "write" ? "side.writes" : "side.reads");
             }).join(t("side.and")) +
             " · " + escapeHtml(t("side.with_others", { n: s.microfrontends.length - 1 })) + "</span>" +
             sliceDetection(s.id) + "</li>";
    });

    var found = (detectionsOf[id] || []).map(function (d) {
      var dimension = textOf(d, "dimension");
      return '<li><span class="ap-tag ap-' + (DATA.colors || {})[d.anti_pattern] + '">' + escapeHtml(d.anti_pattern) + "</span>" +
             (dimension ? " · " + escapeHtml(dimension) : "") + out("detections", String(d.index)) + "</li>";
    });

    side.innerHTML =
      '<div class="body">' +
      "<h3>" + escapeHtml(item.id) + out("microfrontends", id) + "</h3>" +
      (item.role === "shell"
        ? '<span class="badge shell">' + escapeHtml(t("badge.shell")) + "</span>"
        : '<span class="badge">' + escapeHtml(t("side.microfrontend")) + "</span>") +
      // A signal, not a verdict: the exposed module only re-exports, which is
      // the shape of a library. The reader decides what that means.
      (item.reexports
        ? '<span class="badge lib" title="' + escapeHtml(t("side.reexports_title", { n: item.reexports })) + '">' +
          escapeHtml(t("side.reexports", { n: item.reexports })) + "</span>"
        : "") +
      '<div class="summary">' +
        cell(item.screens.length, t("side.screens") + (item.screens.length ? out("screens", id, true) : "")) +
        cell(item.fragments.length, t("side.fragments") + (item.fragments.length ? out("fragments", id, true) : "")) +
        cell(item.degree.in, t("side.incoming")) +
        cell(item.degree.out, t("side.outgoing")) +
        cell(item.detections, t("side.detections") + (item.detections ? out("detections", id, true) : "")) +
      "</div>" +
      group(t("side.size"),
        escapeHtml(t("side.size_value", { lines: number(item.size.code_lines), files: number(item.size.files) })) +
        ' <span class="mono">' + escapeHtml(t("side.physical", { n: number(item.size.lines) })) + "</span>") +
      group(t("side.routes"), "<code>" + escapeHtml(item.routes.join(", ") || "—") + "</code>") +
      group(t("side.screen_list", { n: item.screens.length }), list(screens)) +
      group(t("side.fragment_list", { n: item.fragments.length }), list(fragments)) +
      group(t("side.dependencies"), deps || '<p class="empty">' + t("side.none_f") + "</p>") +
      group(t("side.state", { n: slices.length }), list(slices, t("side.none_m"))) +
      group(t("side.services", { n: endpoints.length }), list(endpoints)) +
      group(t("side.antipatterns"), list(found, t("side.none_m"))) +
      group(t("side.origin"), "<code>" + escapeHtml(item.entrypoint || item.directory || "—") + "</code>") +
      "</div>";
  }

  function showEdge(ids) {
    var wanted = {};
    ids.forEach(function (id) { wanted[id] = true; });
    var items = DATA.edges.filter(function (e) { return wanted[e.edge]; });
    if (!items.length) return;
    redraw = function () { showEdge(ids); };

    // One line in the drawing summarizes several occurrences in the code. The
    // panel unfolds it: what goes through it, in each direction, and where.
    var byDirection = {};
    items.forEach(function (e) {
      var key = e.source + "\u0000" + e.target;
      (byDirection[key] = byDirection[key] || []).push(e);
    });

    var sections = Object.keys(byDirection).sort().map(function (key) {
      var group_ = byDirection[key];
      var first = group_[0];
      var labels = [];
      group_.forEach(function (e) {
        if (e.label && labels.indexOf(e.label) === -1) labels.push(e.label);
      });
      var occurrences = group_.filter(function (e) { return e.file; }).map(function (e) {
        var renders = (e.renders || []).map(function (r) {
          return "<li>" + escapeHtml(t("side.rendered_at", { where: r.file + ":" + r.line })) +
                 " · " + escapeHtml(r.screens && r.screens.length
                   ? t("side.appears_on", { screens: r.screens.join(", ") })
                   : t("side.no_screen")) +
                 (r.props && r.props.length ? " · " + escapeHtml(t("side.props", { props: r.props.join(", ") })) : "") +
                 "</li>";
        }).join("");
        return '<div class="occurrence">' + where(e) +
               (e.detail ? '<p class="mono">' + escapeHtml(detailText(e.detail)) + "</p>" : "") +
               snippet(e) + (renders ? "<ul>" + renders + "</ul>" : "") + "</div>";
      }).join("");
      return '<div class="flow">' + (byId[first.source] ? mfeLink(first.source) : escapeHtml(shortOf(first.source))) +
             " → " + (byId[first.target] ? mfeLink(first.target) : escapeHtml(shortOf(first.target))) +
             relationOut(first.relation, first.source, first.target) + "</div>" +
             '<p class="meaning">' + escapeHtml(meaning(first.relation, shortOf(first.source), shortOf(first.target))) + "</p>" +
             group(usedHeading(first.relation, labels.length),
                   list(labels.map(function (l) { return "<li><code>" + escapeHtml(l) + "</code></li>"; }))) +
             group(t("side.occurrences", { n: group_.length }), occurrences);
    }).join("");

    side.innerHTML = '<div class="body"><h3>' + titleOf(items[0].relation) + "</h3>" + sections + "</div>";
  }

  function titleOf(relation) { return t("side.title." + relation); }

  function usedHeading(relation, count) { return t("side.used." + relation, { n: count }); }

  function showSlot(id, relation) {
    redraw = function () { showSlot(id, relation); };
    if (relation === "state") {
      var slice = DATA.slices.filter(function (s) { return s.id === id; })[0];
      if (!slice) return;
      var rows = slice.accesses.map(function (a) {
        return '<div class="occurrence"><strong>' + mfeLink(a.microfrontend) +
               "</strong> " + escapeHtml(t(a.access === "write" ? "side.writes" : "side.reads")) + " · " + where(a) +
               snippet(a) + "</div>";
      }).join("");
      side.innerHTML = '<div class="body"><h3>' + escapeHtml(slice.path) + sliceDetection(slice.id) + "</h3>" +
        '<span class="badge">' + escapeHtml(slice.library) + "</span>" +
        group(t("side.slice_mfes", { n: slice.microfrontends.length }),
              list(slice.microfrontends.map(function (m) { return "<li>" + mfeLink(m) + "</li>"; }))) +
        group(t("side.accesses", { n: slice.accesses.length }), rows) + "</div>";
      return;
    }

    var endpoint = DATA.endpoints.filter(function (e) { return e.path === id; })[0];
    if (!endpoint) return;
    var calls = DATA.api_calls.filter(function (c) { return c.path === id; }).map(function (c) {
      return '<div class="occurrence"><strong>' + mfeLink(c.microfrontend) + "</strong> " +
             '<span class="mono">' + escapeHtml(c.method) + "</span>" +
             (c.screens && c.screens.length ? " · " + escapeHtml(t("side.on_screen", { screens: c.screens.join(", ") })) : "") +
             " · " + where(c) + snippet(c) + "</div>";
    }).join("");
    side.innerHTML = '<div class="body"><h3><code>' + escapeHtml(endpoint.path) + "</code>" +
      out("api_calls", endpoint.path) + "</h3>" +
      '<span class="badge">' + escapeHtml(endpoint.methods.join(", ")) + "</span>" +
      group(t("side.consumed_by", { n: endpoint.callers.length }),
            list(endpoint.callers.map(function (m) { return "<li>" + mfeLink(m) + "</li>"; }))) +
      group(t("side.calls"), calls) + "</div>";
  }

  function showScreen(id) {
    redraw = function () { showScreen(id); };
    var screen = DATA.screens[id];
    var owner = screen ? screen.microfrontend : id;

    var outgoing = DATA.screen_edges.filter(function (e) { return e.source === id; });
    var incoming = DATA.screen_edges.filter(function (e) { return e.target === id; });

    function rows(edges, other, arrow) {
      return edges.map(function (e) {
        return '<div class="dep"><span class="dir">' + arrow + "</span>" +
               '<a href="#" data-screen-edge-link="' + escapeHtml(e.id) + '">' + placeOf(e[other]) + "</a>" +
               '<span class="kind">' + relationName(e.relation) + "</span></div>" +
               (e.labels.length ? '<p class="mono labels">' + escapeHtml(e.labels.join(", ")) + "</p>" : "");
      }).join("");
    }

    var calls = [];
    if (screen && screen.kind === "screen") {
      var seen = {};
      DATA.api_calls.forEach(function (c) {
        if (c.microfrontend !== owner || (c.screens || []).indexOf(screen.name) === -1) return;
        var key = c.method + c.path;
        if (seen[key]) return;
        seen[key] = true;
        calls.push('<li><span class="mono">' + escapeHtml(c.method) + "</span> <code>" +
                   escapeHtml(c.path) + "</code>" + out("api_calls", c.path) + "</li>");
      });
    }

    side.innerHTML = '<div class="body">' +
      "<h3>" + escapeHtml(screen ? screen.name : t("side.outside")) +
      (screen && screen.kind === "screen" ? out("screens", id) : "") + "</h3>" +
      '<span class="badge">' + escapeHtml(t("side.kind." + (screen ? screen.kind : "outside"))) +
      "</span> " + '<span class="badge">' + mfeLink(owner) + "</span>" +
      (screen && screen.route ? group(t("side.route"), "<code>" + escapeHtml(screen.route) + "</code>") : "") +
      (screen && screen.file ? group(t("side.file"), where(screen)) : "") +
      (!screen ? '<p class="empty">' + escapeHtml(t("side.outside_note")) + "</p>" : "") +
      group(t("side.from_here", { n: outgoing.length }),
            rows(outgoing, "target", "→") || '<p class="empty">' + t("side.nothing") + "</p>") +
      group(t("side.to_here", { n: incoming.length }),
            rows(incoming, "source", "←") || '<p class="empty">' + t("side.nothing") + "</p>") +
      (screen && screen.kind === "screen"
        ? group(t("side.screen_calls", { n: calls.length }), list(calls, t("side.none_m")))
        : "") +
      "</div>";
  }

  function showScreenEdge(id) {
    var edge = DATA.screen_edges.filter(function (e) { return e.id === id; })[0];
    if (!edge) return;
    redraw = function () { showScreenEdge(id); };
    var occurrences = edge.items.map(function (item) {
      return '<div class="occurrence">' + where(item) +
             (item.detail ? '<p class="mono">' + escapeHtml(detailText(item.detail)) + "</p>" : "") +
             snippet(item) + "</div>";
    }).join("");
    side.innerHTML = '<div class="body"><h3>' + titleOf(edge.relation) + "</h3>" +
      '<div class="flow">' + placeOf(edge.source) + "<br>↓<br>" + placeOf(edge.target) + "</div>" +
      '<p class="meaning">' + escapeHtml(meaning(edge.relation, nameOf(edge.source), nameOf(edge.target), true)) + "</p>" +
      group(usedHeading(edge.relation, edge.labels.length),
            list(edge.labels.map(function (l) { return "<li><code>" + escapeHtml(l) + "</code></li>"; }))) +
      group(t("side.occurrences", { n: edge.items.length }), occurrences) +
      "</div>";
  }

  function pin(key) {
    state.pinned = key;
    state.focus = null;
    apply();
  }

  // The sidebar only opens on a click (on a node, an edge, a shortcut),
  // never on mouse hover.
  function openSide() {
    drawer.classList.add("open");
    drawer.setAttribute("aria-hidden", "false");
  }

  // The path inside the sidebar: each of its links (the slice, the screen, the
  // relation between screens) keeps what was open, and ← goes back one
  // step. A click on the graph or on a table starts a new path.
  var trail = [];
  var back = document.getElementById("side-back");

  function showBack() { back.classList.toggle("hidden", !trail.length); }

  function restart() { trail = []; showBack(); }

  function step() {
    if (redraw) trail.push({ draw: redraw, pinned: state.pinned });
    showBack();
  }

  back.addEventListener("click", function () {
    var previous = trail.pop();
    showBack();
    if (!previous) return;
    previous.draw();
    pin(previous.pinned);
  });

  function closeSide() {
    drawer.classList.remove("open");
    drawer.setAttribute("aria-hidden", "true");
    redraw = null;
    restart();
    if (state.pinned) pin(null);
  }

  document.getElementById("side-close").addEventListener("click", closeSide);

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && drawer.classList.contains("open")) closeSide();
  });

  // ------------------------------------------------------------- focus

  // A table row may join several detections (one per route):
  // the focus is their union.
  function focusOn(indices) {
    var found = indices.map(function (i) { return DATA.detections[i]; }).filter(Boolean);
    if (!found.length) return;
    var detection = found[0];

    var nodes = {};
    var edges = {};
    found.forEach(function (item) {
      (item.subjects || []).forEach(function (s) { nodes[s] = true; });
      (item.edges || []).forEach(function (e) { edges[e] = true; });
      if ((item.metadata || {}).path) nodes[item.metadata.path] = true;
    });

    // The evidence of each anti-pattern is in one view: the shared
    // state in the state bipartite, the hammered endpoint in the
    // backend one, the rest in the overview.
    var target = { "global-state-communication": "state",
                   "hammering-apis": "backend" }[detection.anti_pattern] || "overview";

    state.focus = { nodes: nodes, edges: Object.keys(edges).length ? edges : null };
    state.pinned = null;
    state.search = "";
    state.onlyFlagged = false;
    document.getElementById("search").value = "";
    document.getElementById("only-flagged").checked = false;

    state.focusIndex = indices;
    bannerText.textContent = bannerOf(indices);

    show(viewOf(target) ? target : "overview");
    apply();
    reveal();
  }

  // The detection text through the reference the rule left; the stored
  // sentence remains for artifacts from an earlier version.
  function textOf(detection, field) {
    var reference = ((detection.metadata || {}).text || {})[field];
    return reference ? t(reference) : detection[field];
  }

  function bannerOf(indices) {
    var detection = DATA.detections[indices[0]];
    if (indices.length > 1) return detection.anti_pattern + " — " + t("focus.many", { n: indices.length });
    return detection.anti_pattern + " — " + textOf(detection, "message");
  }

  function clearFocus() {
    state.focus = null;
    state.focusIndex = null;
    apply();
  }

  // ---------------------------------------------------------- events

  stage.addEventListener("click", function (event) {
    var edge = event.target.closest(".edge-group");
    var node = event.target.closest(".node, .slot, .screen-node, .cluster");

    if (node) {
      var key = keyOf(node);
      // Clicking again on what is pinned unpins and closes it.
      if (state.pinned === key) { closeSide(); return; }
      if (node.classList.contains("slot")) showSlot(key, node.classList.contains("state") ? "state" : "backend");
      else if (node.classList.contains("screen-node")) showScreen(key);
      else showMicroFrontend(key);
      pin(key);
      restart();
      openSide();
      return;
    }

    if (edge) {
      if (edge.dataset.screenEdge) showScreenEdge(edge.dataset.screenEdge);
      else if (edge.dataset.slot) showSlot(edge.dataset.slot, edge.dataset.relation);
      else if (edge.dataset.edges) showEdge(edge.dataset.edges.split(" "));
      restart();
      openSide();
      return;
    }

    if (event.target.closest("svg") && state.pinned) pin(null);
  });

  side.addEventListener("click", function (event) {
    var link = event.target.closest("[data-screen-link], [data-slot-link], [data-screen-edge-link], [data-mfe-link], [data-page-link]");
    if (!link) return;
    event.preventDefault();
    if (link.dataset.pageLink) {
      closeSide();
      openRow(link.dataset.pageLink, link.dataset.row, !!link.dataset.only);
    } else if (link.dataset.mfeLink) {
      step();
      showMicroFrontend(link.dataset.mfeLink);
      pin(link.dataset.mfeLink);
    } else if (link.dataset.screenLink) {
      step();
      show("screens");
      showScreen(link.dataset.screenLink);
      pin(link.dataset.screenLink);
      reveal();
    } else if (link.dataset.slotLink) {
      step();
      show("state");
      showSlot(link.dataset.slotLink, "state");
      pin(link.dataset.slotLink);
      reveal();
    } else if (link.dataset.screenEdgeLink) {
      step();
      showScreenEdge(link.dataset.screenEdgeLink);
    }
  });

  // Slice per micro frontend: swaps the drawing for the slice's one, which
  // comes ready in a <template>.
  var originals = {};

  function choose(view, key) {
    var viewport = view.querySelector(".viewport");
    var id = view.dataset.view;
    if (!originals[id]) originals[id] = viewport.querySelector("svg");
    var template = key && view.querySelector('template[data-variant="' + cssEscape(key) + '"]');
    var next = template ? template.content.firstElementChild.cloneNode(true) : originals[id];
    viewport.replaceChild(next, viewport.querySelector("svg"));
    var select = view.querySelector("select.variant");
    if (select) select.value = template ? key : "";
    state.variant[id] = template ? key : null;
    remember();
    delete state.zoom[id];
    fit(view);
    apply();
  }

  function cssEscape(value) {
    return String(value).replace(/["\\]/g, "\\$&");
  }

  document.querySelectorAll("select.variant").forEach(function (select) {
    select.addEventListener("change", function () {
      choose(select.closest(".view"), select.value);
    });
  });

  document.getElementById("search").addEventListener("input", function (e) {
    state.search = e.target.value;
    state.pinned = null;
    apply();
  });

  document.getElementById("only-flagged").addEventListener("change", function (e) {
    state.onlyFlagged = e.target.checked;
    apply();
  });

  document.getElementById("show-mount").addEventListener("change", function (e) {
    stage.classList.toggle("no-mount", !e.target.checked);
  });

  document.getElementById("clear-focus").addEventListener("click", clearFocus);

  document.querySelectorAll("[data-focus]").forEach(function (button) {
    button.addEventListener("click", function () {
      showPage("home");
      focusOn(button.dataset.focus.split(",").map(Number));
    });
  });

  document.querySelectorAll("[data-select]").forEach(function (row) {
    row.addEventListener("click", function () {
      showPage("home");
      show("overview");
      showMicroFrontend(row.dataset.select);
      pin(row.dataset.select);
      restart();
      openSide();
      reveal();
    });
  });

  document.querySelectorAll("[data-lang]").forEach(function (button) {
    button.addEventListener("click", function () { setLanguage(button.dataset.lang); });
  });

  // `#view=screens` opens straight into a view: a shared link leads
  // to the question, not to the home page.
  var askedPage = (location.hash.match(/page=([\w-]+)/) || [])[1];
  var asked = (location.hash.match(/view=([\w-]+)/) || [])[1];
  var variant = (location.hash.match(/mfe=([^&]+)/) || [])[1];
  // The mounting filter only appears if some graph has mounting.
  document.querySelector(".mount-toggle").classList.toggle(
    "hidden", !document.querySelector('.edge-group[data-relation="mount"]'));

  fitAll();
  apply();

  if (asked && viewOf(asked)) {
    show(asked);
    if (variant && current().querySelector("select.variant")) {
      choose(current(), decodeURIComponent(variant));
    }
    if (!askedPage) reveal();
  }

  if (askedPage) showPage(askedPage);

  if (language !== DEFAULT) setLanguage(language);
})();
