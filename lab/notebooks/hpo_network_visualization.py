import marimo

__generated_with = "0.21.1"
app = marimo.App(width="full", html_head_file="_embed_head.html")


@app.cell
def _():
    import marimo as mo
    import _utils

    return (mo,)


@app.cell
def _(mo):
    import _utils

    token = _utils.resolve_plot_token(mo)
    mo.stop(not token, _utils.auth_prompt_mo(mo))
    return (token,)


@app.cell
def _(token):
    import _utils

    rows = _utils.fetch_plot_data(
        token,
        "Individual",
        {
            "values": ["hpo_terms__identifier"],
            "annotate": {"count": {"count": "id"}},
        },
    )
    return (rows,)


@app.cell
def _():
    import json
    from functools import lru_cache
    from pathlib import Path
    import fastobo
    import networkx as nx
    import warnings

    import _utils

    warnings.filterwarnings(
        "ignore",
        message=r"No path from .* to root node .*",
        category=UserWarning,
    )
    warnings.filterwarnings(
        "ignore",
        message=r"The node .* is not in the graph.*",
        category=UserWarning,
    )

    @lru_cache(maxsize=1)
    def _resolve_hpo_obo_path() -> Path:
        candidates = [
            Path.cwd() / "ontologies" / "hp.obo",
            Path.cwd().parent / "ontologies" / "hp.obo",
            Path.cwd().parent.parent / "ontologies" / "hp.obo",
        ]

        file_path = globals().get("__file__")
        if file_path:
            file_path = Path(file_path).resolve()
            candidates.extend(
                [
                    file_path.parents[2] / "ontologies" / "hp.obo",
                    file_path.parent.parent / "ontologies" / "hp.obo",
                ]
            )

        for candidate in candidates:
            if candidate.is_file():
                return candidate

        raise FileNotFoundError(
            "Could not find ontologies/hp.obo. Start Marimo from the RareIndex "
            "project root, or set the working directory so the repo is on the path."
        )

    @lru_cache(maxsize=1)
    def load_hpo_ontology():
        obo_path = _resolve_hpo_obo_path()
        graph = nx.DiGraph()

        with obo_path.open("rb") as response:
            hpo = fastobo.load(response)

        for frame in hpo:
            if isinstance(frame, fastobo.term.TermFrame):
                term_id = str(frame.id)
                graph.add_node(term_id, name=term_id)
                for clause in frame:
                    if isinstance(clause, fastobo.term.NameClause):
                        graph.nodes[term_id]["name"] = str(clause.name)
                    elif isinstance(clause, fastobo.term.IsAClause):
                        graph.add_edge(term_id, str(clause.term))

        return graph, hpo

    def consolidate_terms(graph, terms, threshold=3):
        working_counts = terms.copy()
        root_node = "HP:0000118"  # Phenotypic abnormality

        invalid_terms = []
        for term in working_counts:
            if term not in graph:
                warnings.warn(
                    f"The node {term} is not in the graph. Removing from consolidation."
                )
                invalid_terms.append(term)

        for term in invalid_terms:
            working_counts.pop(term, None)

        while True:
            rare_terms = [
                term for term, count in working_counts.items() if count < threshold
            ]

            if not rare_terms:
                break

            changes_made = False

            for term in rare_terms:
                if term == root_node:
                    continue

                try:
                    path = nx.shortest_path(graph, term, root_node)
                    if len(path) > 1:
                        parent = path[1]
                        count = working_counts.pop(term)
                        working_counts[parent] = working_counts.get(parent, 0) + count
                        changes_made = True
                except (nx.NetworkXNoPath, IndexError):
                    continue

            if not changes_made:
                break

        return working_counts

    def _shorten_term_name(name: str) -> str:
        cleaned = name.replace("system", "sys.")
        cleaned = cleaned.replace("morphology", "morph.")
        cleaned = cleaned.replace("Abnormality of the", "")
        cleaned = cleaned.replace("abnormality", "")
        cleaned = cleaned.replace("Abnormality of", "")
        cleaned = cleaned.replace("Abnormal", "")
        cleaned = " ".join(cleaned.split())
        if len(cleaned) > 30:
            cleaned = cleaned[:27] + "..."
        return cleaned

    def _term_name(graph, hpo, term_id: str) -> str:
        if term_id in graph:
            return str(graph.nodes[term_id].get("name", term_id))
        for frame in hpo:
            if isinstance(frame, fastobo.term.TermFrame) and str(frame.id) == term_id:
                for clause in frame:
                    if isinstance(clause, fastobo.term.NameClause):
                        return str(clause.name)
        return term_id

    def _node_color(count: int, is_root: bool = False) -> str:
        if is_root:
            return "#1d4ed8"
        if count >= 50:
            return "#1d4ed8"
        if count >= 20:
            return "#2563eb"
        if count >= 10:
            return "#3b82f6"
        if count >= 5:
            return "#60a5fa"
        return "#93c5fd"

    def build_hpo_network_elements(api_rows, min_count=1, consolidation_threshold=12):
        graph, hpo = load_hpo_ontology()
        root_node = "HP:0000118"  # Phenotypic abnormality

        total_assignments = 0
        term_counts = {}
        for row in api_rows:
            identifier = row.get("hpo_terms__identifier")
            if identifier in (None, ""):
                continue

            raw_identifier = str(identifier).strip()
            term_id = (
                raw_identifier
                if raw_identifier.startswith("HP:")
                else f"HP:{raw_identifier}"
            )
            count = int(row.get("count", 0))
            total_assignments += count
            term_counts[term_id] = term_counts.get(term_id, 0) + count

        consolidated_counts = consolidate_terms(
            graph,
            term_counts,
            threshold=consolidation_threshold,
        )

        subgraph = nx.DiGraph()

        for term_id, count in consolidated_counts.items():
            if term_id in graph and count >= min_count:
                name = _shorten_term_name(_term_name(graph, hpo, term_id))
                subgraph.add_node(term_id, name=name, count=count, term_id=term_id)

                try:
                    path = nx.shortest_path(graph, term_id, root_node)
                    for i in range(len(path) - 1):
                        source = path[i]
                        target = path[i + 1]

                        if source not in subgraph:
                            source_count = consolidated_counts.get(source, 0)
                            subgraph.add_node(
                                source,
                                name=_shorten_term_name(_term_name(graph, hpo, source)),
                                count=source_count,
                                term_id=source,
                            )
                        if target not in subgraph:
                            target_count = consolidated_counts.get(target, 0)
                            subgraph.add_node(
                                target,
                                name=_shorten_term_name(_term_name(graph, hpo, target)),
                                count=target_count,
                                term_id=target,
                            )

                        subgraph.add_edge(source, target)
                except nx.NetworkXNoPath:
                    warnings.warn(f"No path from {term_id} to root node {root_node}")

        if root_node not in subgraph:
            subgraph.add_node(
                root_node,
                name=_shorten_term_name(_term_name(graph, hpo, root_node)),
                count=consolidated_counts.get(root_node, 0),
                term_id=root_node,
            )

        elements = []
        for node_id, data in subgraph.nodes(data=True):
            count = int(data.get("count", 0))
            name = str(data.get("name", node_id))
            label = name
            is_root = node_id == root_node
            size = 28 if is_root else max(18, min(80, 18 + int((count or 1) ** 0.5 * 7)))

            node_element = {
                "data": {
                    "id": node_id,
                    "label": label,
                    "count": count,
                    "term_id": data.get("term_id", node_id),
                    "size": size,
                    "color": _node_color(count, is_root=is_root),
                }
            }
            if is_root:
                node_element["classes"] = "root"
            elements.append(node_element)

        for source, target in subgraph.edges():
            elements.append(
                {
                    "data": {
                        "id": f"{source}->{target}",
                        "source": source,
                        "target": target,
                    }
                }
            )

        term_count = len([node for node in subgraph.nodes() if node != root_node])
        return elements, term_count, total_assignments

    def cytoscape_html(
        elements,
        *,
        layout_mode: str,
        theme_mode: str,
        fullscreen: bool = False,
    ):
        cytoscape_js = f"{_utils.DJANGO_API_URL.rstrip('/')}/static/lab/js/cytoscape.min.js"
        cytoscape_svg_js = f"{_utils.DJANGO_API_URL.rstrip('/')}/static/lab/js/cytoscape-svg.min.js"
        elements_json = json.dumps(elements).replace("</", "<\\/")
        layout_mode = "Layered" if str(layout_mode).strip().lower() == "layered" else "Circular"
        theme_mode = "Rainbow" if str(theme_mode).strip().lower() == "rainbow" else "Icefire"
        active_palette = "rainbow" if theme_mode == "Rainbow" else "icefire"
        graph_height = "100%" if fullscreen else "860px"
        wrapper_height = "100%" if fullscreen else "100%"
        fit_padding = 8 if fullscreen else 20
        radial_step = 120 if fullscreen else 80
        layered_spacing = 0.95 if fullscreen else 0.7
        action_buttons_html = """
    <div id="hpo-actions" style="position:absolute;left:0.5rem;top:0.5rem;z-index:5;display:flex;gap:0.35rem;flex-wrap:wrap;">
      <button id="hpo-download-png" type="button" style="border:1px solid #d1d5db;border-radius:0.5rem;background:rgba(255,255,255,0.94);color:#374151;font-size:12px;line-height:1;padding:0.45rem 0.7rem;box-shadow:0 1px 2px rgba(0,0,0,0.06);cursor:pointer;">PNG</button>
      <button id="hpo-download-html" type="button" style="border:1px solid #d1d5db;border-radius:0.5rem;background:rgba(255,255,255,0.94);color:#374151;font-size:12px;line-height:1;padding:0.45rem 0.7rem;box-shadow:0 1px 2px rgba(0,0,0,0.06);cursor:pointer;">HTML</button>
      <button id="hpo-download-svg" type="button" style="border:1px solid #d1d5db;border-radius:0.5rem;background:rgba(255,255,255,0.94);color:#374151;font-size:12px;line-height:1;padding:0.45rem 0.7rem;box-shadow:0 1px 2px rgba(0,0,0,0.06);cursor:pointer;">SVG</button>
    </div>"""

        return f"""
<style>
  html, body {{
    width: 100%;
    height: 100%;
    margin: 0;
    overflow: hidden;
    background: #ffffff;
    font-family: Inter, Arial, sans-serif;
  }}
</style>
<div id="hpo-shell" style="width:100%;height:{wrapper_height};min-height:0;display:flex;flex-direction:column;position:relative;background:#ffffff;">
{action_buttons_html}
    <div id="hpo-cytoscape" style="width:100%;height:{graph_height};min-height:{graph_height};flex:1 1 auto;"></div>
    <div id="hpo-legend" style="display:none;position:absolute;right:0.5rem;top:0.5rem;background:rgba(255,255,255,0.85);border:1px solid #e5e7eb;border-radius:0.375rem;padding:0.5rem;box-shadow:0 1px 2px rgba(0,0,0,0.08);">
      <div style="font-size:0.75rem;color:#374151;margin-bottom:0.25rem;text-align:center;">Count</div>
      <div id="hpo-legend-bar" style="width:14px;height:180px;border-radius:4px;"></div>
      <div style="display:flex;justify-content:space-between;font-size:10px;color:#374151;margin-top:0.25rem;">
        <span id="hpo-legend-min">0</span>
        <span id="hpo-legend-max">0</span>
      </div>
    </div>
  </div>
  <script id="hpo-elements" type="application/json">{elements_json}</script>
  <script src="{cytoscape_js}"></script>
  <script src="{cytoscape_svg_js}"></script>
  <script>
    (function() {{
      try {{
        var raw = document.getElementById('hpo-elements').textContent;
        var elements = JSON.parse(raw);
        var container = document.getElementById('hpo-cytoscape');
        if (!container || !window.cytoscape) {{
          return;
        }}

        var maxCount = 1;
        for (var i = 0; i < elements.length; i++) {{
          var el = elements[i];
          if (el && el.data && typeof el.data.count === 'number' && el.data.count > maxCount) {{
            maxCount = el.data.count;
          }}
        }}

        var palettes = {{
          icefire: ['#000004','#090720','#140b3d','#1f0a52','#2a0a5f','#350a68','#410a6c','#4c0b6b','#570d69','#611368','#6a1a6b','#74206e','#7f2773','#8b2d78','#97357b','#a23d7b','#ad4577','#b74e70','#c15768','#c9615e','#d06c54','#d57849','#d9843f','#dd9036','#e09b2e','#e3a828','#e6b523','#e8c220','#ebd01f','#efdd22','#f3ea2a','#f8f338','#fcf951'],
          rainbow: ['#9400D3','#4B0082','#0000FF','#00FFFF','#00FF00','#FFFF00','#FF7F00','#FF0000']
        }};

        function lerpColor(c1, c2, t) {{
          function h2i(h) {{ return parseInt(h, 16); }}
          function i2h(i) {{ var s = i.toString(16); return s.length === 1 ? '0' + s : s; }}
          var r = h2i(c1.substr(1, 2)), g = h2i(c1.substr(3, 2)), b = h2i(c1.substr(5, 2));
          var r2 = h2i(c2.substr(1, 2)), g2 = h2i(c2.substr(3, 2)), b2 = h2i(c2.substr(5, 2));
          var rn = Math.round(r + (r2 - r) * t), gn = Math.round(g + (g2 - g) * t), bn = Math.round(b + (b2 - b) * t);
          return '#' + i2h(rn) + i2h(gn) + i2h(bn);
        }}

        function interpPalette(palette, t) {{
          if (t <= 0) return palette[0];
          if (t >= 1) return palette[palette.length - 1];
          var pos = t * (palette.length - 1);
          var i = Math.floor(pos);
          var f = pos - i;
          return lerpColor(palette[i], palette[i + 1], f);
        }}

        function buildRadialPositions(cy, rStep) {{
          var rootId = 'HP:0000118';
          var children = {{}};
          cy.nodes().forEach(function(n) {{ children[n.id()] = []; }});
          cy.edges().forEach(function(e) {{
            var s = e.data('source');
            var t = e.data('target');
            if (children[t]) {{ children[t].push(s); }}
          }});

          var subtreeSize = {{}};
          function dfsSize(node) {{
            var kids = children[node] || [];
            var size = 1;
            for (var i = 0; i < kids.length; i++) {{
              size += dfsSize(kids[i]);
            }}
            subtreeSize[node] = size;
            return size;
          }}
          dfsSize(rootId);

          var positions = {{}};
          function assign(node, depth, startA, endA) {{
            var mid = (startA + endA) / 2;
            positions[node] = {{
              x: Math.cos(mid) * depth * rStep,
              y: Math.sin(mid) * depth * rStep
            }};
            var kids = children[node] || [];
            if (!kids.length) return;
            var total = 0;
            for (var i = 0; i < kids.length; i++) {{
              total += (subtreeSize[kids[i]] || 1);
            }}
            var cursor = startA;
            for (var j = 0; j < kids.length; j++) {{
              var frac = (subtreeSize[kids[j]] || 1) / total;
              var span = frac * (endA - startA);
              var nextStart = cursor;
              var nextEnd = cursor + span;
              assign(kids[j], depth + 1, nextStart, nextEnd);
              cursor = nextEnd;
            }}
          }}
          assign(rootId, 0, -Math.PI, Math.PI);
          return positions;
        }}

        var cy = cytoscape({{
          container: container,
          elements: elements,
          layout: {{ name: 'preset' }},
          style: [
            {{
              selector: 'node',
              style: {{
                'label': 'data(label)',
                'font-size': 10,
                'text-valign': 'bottom',
                'text-halign': 'center',
                'text-margin-y': 6,
                'text-wrap': 'wrap',
                'text-max-width': 100,
                'width': 'mapData(count, 0, ' + maxCount + ', 8, 48)',
                'height': 'mapData(count, 0, ' + maxCount + ', 8, 48)',
                'background-color': 'data(color)',
                'color': '#111827'
              }}
            }},
            {{
              selector: 'node.root',
              style: {{
                'border-width': 2,
                'border-color': '#1e3a8a'
              }}
            }},
            {{
              selector: 'edge',
              style: {{
                'curve-style': 'bezier',
                'width': 1,
                'line-color': '#9CA3AF',
                'opacity': 0.7
              }}
            }}
          ]
        }});

        var activePalette = palettes[{json.dumps(active_palette)}];

        function triggerDownload(href, filename) {{
          var a = document.createElement('a');
          a.href = href;
          a.download = filename;
          document.body.appendChild(a);
          a.click();
          a.remove();
        }}

        function downloadBlob(blob, filename) {{
          var url = URL.createObjectURL(blob);
          triggerDownload(url, filename);
          setTimeout(function () {{
            URL.revokeObjectURL(url);
          }}, 1000);
        }}

        function exportPngData() {{
          return cy.png({{ full: true, scale: 2, bg: '#ffffff' }});
        }}

        function exportHtmlText() {{
          return '<!doctype html>\\n' + document.documentElement.outerHTML;
        }}

        function exportSvgText() {{
          if (typeof cy.svg !== 'function') {{
            throw new Error('Cytoscape SVG export is unavailable.');
          }}
          return cy.svg({{ full: true, bg: '#ffffff' }});
        }}

        function downloadPng() {{
          triggerDownload(exportPngData(), 'hpo-network.png');
        }}

        function downloadHtml() {{
          downloadBlob(
            new Blob([exportHtmlText()], {{ type: 'text/html;charset=utf-8' }}),
            'hpo-network.html'
          );
        }}

        function downloadSvg() {{
          downloadBlob(
            new Blob([exportSvgText()], {{ type: 'image/svg+xml;charset=utf-8' }}),
            'hpo-network.svg'
          );
        }}

        cy.nodes().forEach(function(n) {{
          var c = n.data('count') || 0;
          var t = maxCount > 0 ? (c / maxCount) : 0;
          n.data('color', interpPalette(activePalette, t));
        }});
        cy.style().selector('node').style('background-color', 'data(color)').update();

        var grad = 'linear-gradient(to top, ' + activePalette.slice().reverse().join(',') + ')';
        var bar = document.getElementById('hpo-legend-bar');
        if (bar) {{ bar.style.background = grad; }}
        var minL = document.getElementById('hpo-legend-min');
        if (minL) {{ minL.textContent = '0'; }}
        var maxL = document.getElementById('hpo-legend-max');
        if (maxL) {{ maxL.textContent = String(maxCount); }}
        var legend = document.getElementById('hpo-legend');
        if (legend) {{ legend.style.display = 'block'; }}

        var pngButton = document.getElementById('hpo-download-png');
        if (pngButton) {{
          pngButton.addEventListener('click', function () {{
            try {{
              downloadPng();
            }} catch (e) {{
              console.error('HPO PNG export failed', e);
            }}
          }});
        }}

        var htmlButton = document.getElementById('hpo-download-html');
        if (htmlButton) {{
          htmlButton.addEventListener('click', function () {{
            try {{
              downloadHtml();
            }} catch (e) {{
              console.error('HPO HTML export failed', e);
            }}
          }});
        }}

        var svgButton = document.getElementById('hpo-download-svg');
        if (svgButton) {{
          svgButton.addEventListener('click', function () {{
            try {{
              downloadSvg();
            }} catch (e) {{
              console.error('HPO SVG export failed', e);
            }}
          }});
        }}

        function fitGraph() {{
          cy.resize();
          cy.fit(cy.elements(), {fit_padding});
        }}

        if ({json.dumps(layout_mode)} === 'Layered') {{
          cy.layout({{
            name: 'breadthfirst',
            directed: false,
            roots: '[id = "HP:0000118"]',
            spacingFactor: {layered_spacing},
            padding: 0,
            animate: false,
            nodeDimensionsIncludeLabels: false,
            avoidOverlap: true,
            fit: false
          }}).run();
        }} else {{
          var positions = buildRadialPositions(cy, {radial_step});
          cy.layout({{
            name: 'preset',
            positions: function(n) {{
              var p = positions[n.id()];
              return p ? p : n.position();
            }},
            animate: false,
            fit: false
          }}).run();
        }}

        fitGraph();
        cy.ready(fitGraph);

        if (window.ResizeObserver) {{
          var shell = document.getElementById('hpo-shell');
          if (shell) {{
            var observer = new ResizeObserver(function () {{
              window.requestAnimationFrame(fitGraph);
            }});
            observer.observe(shell);
          }}
        }}

        window.addEventListener('resize', fitGraph);
      }} catch (e) {{
        console.error('Cytoscape init error', e);
      }}
    }})();
  </script>
  </div>
    """

    return build_hpo_network_elements, cytoscape_html


@app.cell
def _(mo):
    import _utils

    qp = mo.query_params()
    layout_mode = str(_utils._qp_get(qp, "layout", "Circular")).strip() or "Circular"
    theme_mode = str(_utils._qp_get(qp, "theme", "Icefire")).strip() or "Icefire"
    fullscreen = str(_utils._qp_get(qp, "fullscreen", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    try:
        consolidation_threshold = int(_utils._qp_get(qp, "threshold", 12))
    except (TypeError, ValueError):
        consolidation_threshold = 12
    consolidation_threshold = max(1, min(24, consolidation_threshold))
    layout_mode = "Layered" if layout_mode.lower() == "layered" else "Circular"
    theme_mode = "Rainbow" if theme_mode.lower() == "rainbow" else "Icefire"
    return layout_mode, theme_mode, consolidation_threshold, fullscreen


@app.cell
def _(build_hpo_network_elements, cytoscape_html, layout_mode, consolidation_threshold, fullscreen, mo, rows, theme_mode):
    mo.stop(not rows, mo.md("_No HPO term rows returned for this query._"))

    try:
        elements, _, _ = build_hpo_network_elements(
            rows,
            consolidation_threshold=consolidation_threshold,
        )
        output = mo.iframe(
            cytoscape_html(
                elements,
                layout_mode=layout_mode,
                theme_mode=theme_mode,
                fullscreen=fullscreen,
            ),
            height="calc(100vh - 8rem)" if fullscreen else "940px",
        )
    except Exception as exc:
        output = mo.md(f"_Failed to render HPO network: `{exc}`_")
    output
    return


if __name__ == "__main__":
    app.run()
