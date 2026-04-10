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
            "values": [
                "statuses__name",
                "samples__statuses__name",
                "samples__tests__statuses__name",
            ],
            "annotate": {"count": {"count": "id"}},
        },
    )
    # Observable Plot.tree expects one slash-separated path field, not multiple columns.
    path_cols = [
        "statuses__name",
        "samples__statuses__name",
        "samples__tests__statuses__name",
    ]

    def _build_plot_rows(api_rows, cols):
        def _seg(v):
            if v is None or v == "":
                return "(empty)"
            return str(v).replace("/", "\u2215")

        built = []
        for api_row in api_rows:
            out = dict(api_row)
            out["tree_path"] = "/".join(_seg(out.get(k)) for k in cols)
            built.append(out)
        return built

    plot_rows = _build_plot_rows(rows, path_cols)
    return (plot_rows,)


@app.cell
def _():
    return


@app.cell
def _(mo, plot_rows):
    # Loop/comprehension names must not collide across cells; keep plot logic inside a function.
    import plotly.graph_objects as go

    mo.stop(
        not plot_rows,
        mo.md("_No rows returned for this query._"),
    )

    def _sunburst_figure(rows_in):
        leaf_counts = {}
        for row in rows_in:
            tp = str(row["tree_path"]).strip()
            if not tp:
                continue
            leaf_counts[tp] = leaf_counts.get(tp, 0) + int(row["count"])
        if not leaf_counts:
            return None

        node_ids = set()
        for path in leaf_counts:
            parts = [p for p in path.split("/") if p != ""]
            for depth in range(len(parts)):
                node_ids.add("/".join(parts[: depth + 1]))

        def subtree_total(nid: str) -> int:
            total = 0
            for leaf_path, c in leaf_counts.items():
                if leaf_path == nid or leaf_path.startswith(nid + "/"):
                    total += c
            return total

        ids = []
        labels = []
        parents = []
        values = []
        for nid in sorted(node_ids, key=lambda nid_key: (nid_key.count("/"), len(nid_key))):
            labels.append(nid.split("/")[-1])
            ids.append(nid)
            parents.append(nid.rsplit("/", 1)[0] if "/" in nid else "")
            values.append(subtree_total(nid))

        fig = go.Figure(
            go.Sunburst(
                ids=ids,
                labels=labels,
                parents=parents,
                values=values,
                branchvalues="total",
                marker=dict(line=dict(color="#e5e7eb", width=1)),
            )
        )
        fig.update_layout(
            autosize=True,
            height=360,
            margin=dict(t=0, l=0, r=0, b=0),
        )
        return fig

    _sunburst_figure(plot_rows)
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
