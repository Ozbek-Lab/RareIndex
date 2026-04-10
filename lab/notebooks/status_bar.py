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

    # Fetch data for status distribution
    data = _utils.fetch_plot_data(
        token,
        "Individual",
        {
            "values": ["statuses__name"],
            "annotate": {"count": {"count": "id"}},
        },
    )
    return (data,)


@app.cell
def _(data, mo):
    import plotly.graph_objects as go

    mo.stop(not data, mo.md("_No rows returned._"))

    def status_bar_figure(api_rows):
        rows_sorted = sorted(
            (
                {
                    "x": "(empty)"
                    if rec.get("statuses__name") in (None, "")
                    else str(rec["statuses__name"]),
                    "y": int(rec["count"]),
                }
                for rec in api_rows
            ),
            key=lambda pt: pt["y"],
            reverse=True,
        )
        total_ct = sum(pt["y"] for pt in rows_sorted)
        fig = go.Figure(
            go.Bar(
                x=[pt["x"] for pt in rows_sorted],
                y=[pt["y"] for pt in rows_sorted],
                marker_color="#4f46e5",
            )
        )
        fig.update_layout(
            autosize=True,
            height=360,
            xaxis_title=None,
            yaxis_title="Count",
            margin=dict(t=8, l=48, r=24, b=100),
            xaxis_tickangle=-35,
        )
        return fig

    return (status_bar_figure,)


@app.cell
def _(data, status_bar_figure):
    status_bar_figure(data)
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
