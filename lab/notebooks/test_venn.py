import marimo

__generated_with = "0.21.1"
app = marimo.App(width="full", html_head_file="_embed_head.html")


@app.cell
def _():
    import marimo as mo
    import _utils as plot_utils
    import _test_overlap as test_overlap

    return mo, plot_utils, test_overlap


@app.cell
def _(mo, plot_utils):
    token = plot_utils.resolve_plot_token(mo)
    mo.stop(not token, plot_utils.auth_prompt_mo(mo))
    return (token,)


@app.cell
def _(token, plot_utils, test_overlap):
    individual_rows = plot_utils.fetch_plot_data(
        token, "Individual", {"values": test_overlap.INDIVIDUAL_VALUES}
    )
    test_types = plot_utils.fetch_plot_data(token, "TestType", {"values": ["id", "name"]})
    memberships = test_overlap.individual_test_memberships(individual_rows)
    return memberships, test_types


@app.cell
def _(mo, test_types, test_overlap):
    options = test_overlap.test_type_options(test_types)
    default_ids = test_overlap.default_test_types(test_types)
    default_labels = {test_id: label for label, test_id in options.items()}
    selected_tests = mo.ui.multiselect(
        options=options,
        value=[default_labels[test_id] for test_id in default_ids],
        label="Test types",
        full_width=True,
    )
    return options, selected_tests


@app.cell
def _(mo, memberships, options, selected_tests, test_types, plot_utils, test_overlap):
    selected_ids = selected_tests.value
    labels_by_id = {test_id: label for label, test_id in options.items()}
    selected_labels = [labels_by_id[test_id] for test_id in selected_ids]
    counts = test_overlap.overlap_counts(memberships, selected_ids)
    fullscreen = str(plot_utils._qp_get(mo.query_params(), "fullscreen", "")).lower() in {
        "1", "true", "yes", "on",
    }
    figure = test_overlap.overlap_figure(counts, selected_labels, fullscreen)
    note = (
        "With six or more types, circles show a schematic overview and the legend gives test totals. "
        "Not every intersection can be drawn; use the table for all exact combination counts."
        if len(selected_ids) > 5 else
        "Each region shows an exact combination of the selected tests. Shape areas are not proportional to counts."
    )
    messages = []
    if not test_types:
        messages.append(mo.md("No test types are configured yet."))
    if not memberships:
        messages.append(mo.md("No individuals match your current filters and access permissions."))
    mo.vstack([
        mo.md("### Individuals by Test Type"),
        selected_tests,
        mo.md(
            f"**Individuals in cohort: {len(memberships):,}** · "
            f"With any selected test: {len(memberships) - counts[0]:,} · "
            f"With none: {counts[0]:,}"
        ),
        *messages,
        mo.as_html(figure),
        mo.md(note + " Individuals are counted once across all samples. Unselected test types do not affect membership."),
        mo.ui.table(
            test_overlap.overlap_table(counts, selected_labels),
            label="Exact test combinations",
            selection=None,
            page_size=10,
        ),
    ])
    return


if __name__ == "__main__":
    app.run()
