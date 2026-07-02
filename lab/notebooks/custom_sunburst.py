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
def _():
    FIELD_OPTIONS = {
        "Individual": {
            "Index status": "is_index",
            "Affected status": "is_affected",
            "Alive status": "is_alive",
            "Sex": "sex",
            "Individual status group": "statuses__name",
            "Project involvement": "projects__name",
            "Sample status group": "samples__statuses__name",
            "Test status group": "samples__tests__statuses__name",
            "Available tests": "samples__tests__test_type__name",
            "Tests with variants": "samples__tests__pipelines__analyses__found_variants__analysis__pipeline__test__test_type__name",
        },
        "Sample": {
            "Sample type": "sample_type__name",
            "Sample status group": "statuses__name",
            "Individual index status": "individual__is_index",
            "Individual affected status": "individual__is_affected",
            "Individual status group": "individual__statuses__name",
            "Test status group": "tests__statuses__name",
        },
        "Test": {
            "Test type": "test_type__name",
            "Test status group": "statuses__name",
            "Sample type": "sample__sample_type__name",
            "Sample status group": "sample__statuses__name",
            "Individual status group": "sample__individual__statuses__name",
            "Individual affected status": "sample__individual__is_affected",
        },
        "Pipeline": {
            "Pipeline type": "type__name",
            "Pipeline status group": "statuses__name",
            "Test status group": "test__statuses__name",
            "Sample status group": "test__sample__statuses__name",
            "Individual status group": "test__sample__individual__statuses__name",
        },
        "Analysis": {
            "Analysis type": "type__name",
            "Analysis status group": "statuses__name",
            "Pipeline type": "pipeline__type__name",
            "Pipeline status group": "pipeline__statuses__name",
            "Test status group": "pipeline__test__statuses__name",
            "Sample status group": "pipeline__test__sample__statuses__name",
            "Individual status group": "pipeline__test__sample__individual__statuses__name",
        },
        "Project": {
            "Project name": "name",
            "Project priority": "priority",
            "Project status group": "statuses__name",
            "Project creator": "created_by__username",
        },
        "Variant": {
            "Variant status group": "statuses__name",
            "Variant zygosity": "zygosity",
            "Assembly version": "assembly_version",
            "Chromosome": "chromosome",
            "Analysis type": "analysis__type__name",
            "Created by": "created_by__username",
        },
    }

    MODEL_DEFAULT_FIELDS = {
        "Individual": ["Index status", "Affected status", "Individual status group"],
        "Sample": ["Sample type", "Sample status group", "Individual affected status"],
        "Test": ["Test type", "Test status group", "Sample status group"],
        "Pipeline": ["Pipeline type", "Pipeline status group", "Test status group"],
        "Analysis": ["Analysis type", "Analysis status group", "Pipeline status group"],
        "Project": ["Project priority", "Project status group", "Project creator"],
        "Variant": ["Variant zygosity", "Assembly version", "Variant status group"],
    }

    def _boolean_labels_for_field(field):
        field_name = str(field or "").split("__")[-1]
        if field_name == "is_index":
            return "Index", "Not Index"
        if field_name == "is_affected":
            return "Affected", "Not Affected"
        if field_name == "is_alive":
            return "Alive", "Not Alive"
        if field_name.startswith("is_"):
            base = field_name.removeprefix("is_").replace("_", " ").strip().title()
            return base or "Yes", f"Not {base}" if base else "No"
        return "Yes", "No"

    def _normalize_sunburst_value(value, field=None):
        true_label, false_label = _boolean_labels_for_field(field)
        if isinstance(value, bool):
            return true_label if value else false_label
        if value in (None, ""):
            return "(empty)"
        text = str(value).strip()
        if not text:
            return "(empty)"
        lowered = text.lower()
        if lowered in {"true", "false"}:
            return true_label if lowered == "true" else false_label
        return text.replace("/", "\u2215")

    def build_filter_options(api_rows, fields):
        from collections import Counter

        options = {}
        for field in fields:
            counts = Counter(
                _normalize_sunburst_value(api_row.get(field), field)
                for api_row in api_rows
            )
            ordered = sorted(counts, key=lambda value: (-counts[value], value))
            options[field] = ordered or ["(empty)"]
        return options

    def build_plot_rows(api_rows, fields, include_values_by_field=None):
        include_values_by_field = include_values_by_field or {}
        built = []
        for api_row in api_rows:
            out = dict(api_row)
            normalized_values = {
                field: _normalize_sunburst_value(out.get(field), field)
                for field in fields
            }
            if any(
                field in include_values_by_field
                and normalized_values.get(field) not in include_values_by_field[field]
                for field in fields
            ):
                continue
            out["tree_path"] = "/".join(normalized_values[field] for field in fields)
            built.append(out)
        return built

    def sunburst_texttemplate(show_counts=False, show_percentages=False):
        if show_counts and show_percentages:
            return "%{label}<br>%{customdata[0]} (%{customdata[1]})"
        if show_counts:
            return "%{label}<br>%{customdata[0]}"
        if show_percentages:
            return "%{label}<br>%{customdata[1]}"
        return "%{label}"

    def sunburst_figure(
        rows_in,
        fields,
        fullscreen=False,
        show_counts=False,
        show_percentages=False,
    ):
        import plotly.graph_objects as go

        leaf_counts = {}
        for row in rows_in:
            tp = str(row.get("tree_path", "")).strip()
            if not tp:
                continue
            leaf_counts[tp] = leaf_counts.get(tp, 0) + int(row.get("count", 0))
        if not leaf_counts:
            return None
        total_count = sum(leaf_counts.values()) or 1

        node_ids = set()
        for path in leaf_counts:
            parts = [part for part in path.split("/") if part != ""]
            for depth in range(len(parts)):
                node_ids.add("/".join(parts[: depth + 1]))

        def subtree_total(node_id: str) -> int:
            total = 0
            for leaf_path, count in leaf_counts.items():
                if leaf_path == node_id or leaf_path.startswith(node_id + "/"):
                    total += count
            return total

        ids = []
        labels = []
        parents = []
        values = []
        customdata = []
        for node_id in sorted(node_ids, key=lambda key: (key.count("/"), len(key))):
            node_value = subtree_total(node_id)
            ids.append(node_id)
            labels.append(node_id.split("/")[-1])
            parents.append(node_id.rsplit("/", 1)[0] if "/" in node_id else "")
            values.append(node_value)
            customdata.append(
                [
                    f"{node_value:,}",
                    f"{(node_value / total_count):.1%}",
                ]
            )

        texttemplate = sunburst_texttemplate(show_counts, show_percentages)

        fig = go.Figure(
            go.Sunburst(
                ids=ids,
                labels=labels,
                parents=parents,
                values=values,
                customdata=customdata,
                branchvalues="total",
                sort=False,
                marker=dict(line=dict(color="#e5e7eb", width=1)),
                insidetextorientation="horizontal",
                texttemplate=texttemplate,
                hovertemplate=f"{texttemplate}<extra></extra>",
            )
        )
        fig.update_layout(
            autosize=True,
            height=1000 if fullscreen else 460,
            margin=dict(t=0, l=0, r=0, b=0),
        )
        return fig

    return (
        FIELD_OPTIONS,
        MODEL_DEFAULT_FIELDS,
        build_plot_rows,
        build_filter_options,
        sunburst_figure,
    )


@app.cell
def _(mo):
    import _utils

    qp = mo.query_params()
    fullscreen = str(_utils._qp_get(qp, "fullscreen", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    default_model = str(_utils._qp_get(qp, "model", "Individual")).strip() or "Individual"
    default_layer1 = str(_utils._qp_get(qp, "layer1", "")).strip()
    default_layer2 = str(_utils._qp_get(qp, "layer2", "")).strip()
    default_layer3 = str(_utils._qp_get(qp, "layer3", "")).strip()
    return (
        default_layer1,
        default_layer2,
        default_layer3,
        default_model,
        fullscreen,
    )


@app.cell
def _(FIELD_OPTIONS, default_model, mo):
    model_selector = mo.ui.dropdown(
        options={name: name for name in FIELD_OPTIONS},
        value=default_model if default_model in FIELD_OPTIONS else "Individual",
        label="Class",
        searchable=True,
    )
    return (model_selector,)


@app.cell
def _(mo):
    show_counts_checkbox = mo.ui.checkbox(value=True, label="Show counts")
    show_percentages_checkbox = mo.ui.checkbox(value=False, label="Show percentages")
    return show_counts_checkbox, show_percentages_checkbox


@app.cell
def _(FIELD_OPTIONS, MODEL_DEFAULT_FIELDS, model_selector):
    selected_model = model_selector.value if model_selector.value in FIELD_OPTIONS else "Individual"
    field_options = FIELD_OPTIONS[selected_model]
    defaults = MODEL_DEFAULT_FIELDS.get(selected_model, list(field_options.values())[:3])
    return defaults, field_options


@app.cell
def _(default_layer1, default_layer2, default_layer3, defaults, field_options):
    value_to_label = {value: label for label, value in field_options.items()}

    def _resolve_layer_value(default_value, index):
        candidate = default_value or (defaults[index] if index < len(defaults) else None)
        if candidate in field_options:
            return field_options[candidate]
        if candidate in value_to_label:
            return candidate
        fallback = defaults[index] if index < len(defaults) else next(iter(field_options.keys()))
        if fallback in field_options:
            return field_options[fallback]
        if fallback in value_to_label:
            return fallback
        return next(iter(field_options.values()))

    initial_layer_values = []
    for index, default_value in enumerate((default_layer1, default_layer2, default_layer3)):
        if default_value:
            resolved = _resolve_layer_value(default_value, index)
            if resolved and resolved not in initial_layer_values:
                initial_layer_values.append(resolved)

    if not initial_layer_values:
        initial_layer_values = [_resolve_layer_value(None, 0)]

    return initial_layer_values, value_to_label


@app.cell
def _(initial_layer_values, mo):
    layer_rows_state, set_layer_rows_state = mo.state(
        [
            {"id": index + 1, "field": field}
            for index, field in enumerate(initial_layer_values)
        ],
        allow_self_loops=True,
    )
    next_layer_id_state, set_next_layer_id_state = mo.state(
        len(initial_layer_values) + 1,
        allow_self_loops=True,
    )
    return (
        layer_rows_state,
        set_layer_rows_state,
        next_layer_id_state,
        set_next_layer_id_state,
    )


@app.cell
def _(mo):
    filter_rows_state, set_filter_rows_state = mo.state([], allow_self_loops=True)
    next_filter_id_state, set_next_filter_id_state = mo.state(1, allow_self_loops=True)
    active_model_state, set_active_model_state = mo.state(None, allow_self_loops=True)
    return (
        filter_rows_state,
        set_filter_rows_state,
        next_filter_id_state,
        set_next_filter_id_state,
        active_model_state,
        set_active_model_state,
    )


@app.cell
def _(field_options, filter_rows_state, next_filter_id_state, set_filter_rows_state, set_next_filter_id_state):
    def add_filter_row(_=None):
        current_rows = filter_rows_state()
        existing_fields = {
            row.get("field")
            for row in current_rows
            if row.get("field")
        }
        available_fields = [
            value
            for value in field_options.values()
            if value not in existing_fields
        ]
        default_field = available_fields[0] if available_fields else None
        default_values = None
        row_id = next_filter_id_state()
        set_next_filter_id_state(row_id + 1)
        set_filter_rows_state(
            current_rows
            + [{"id": row_id, "field": default_field, "values": default_values}]
        )

    def update_filter_row(row_id, **updates):
        updated = []
        for row in filter_rows_state():
            if row["id"] == row_id:
                new_row = dict(row)
                new_row.update(updates)
                updated.append(new_row)
            else:
                updated.append(row)
        set_filter_rows_state(updated)

    def remove_filter_row(row_id):
        set_filter_rows_state([row for row in filter_rows_state() if row["id"] != row_id])

    return add_filter_row, remove_filter_row, update_filter_row


@app.cell
def _(field_options, layer_rows_state, next_layer_id_state, set_layer_rows_state, set_next_layer_id_state):
    def add_layer_row(_=None):
        current_rows = layer_rows_state()
        existing_fields = {
            row.get("field")
            for row in current_rows
            if row.get("field")
        }
        available_fields = [
            value
            for value in field_options.values()
            if value not in existing_fields
        ]
        default_field = available_fields[0] if available_fields else None
        row_id = next_layer_id_state()
        set_next_layer_id_state(row_id + 1)
        set_layer_rows_state(
            current_rows + [{"id": row_id, "field": default_field}]
        )

    def update_layer_row(row_id, **updates):
        updated = []
        for row in layer_rows_state():
            if row["id"] == row_id:
                new_row = dict(row)
                new_row.update(updates)
                updated.append(new_row)
            else:
                updated.append(row)
        set_layer_rows_state(updated)

    def remove_layer_row(row_id):
        current_rows = layer_rows_state()
        if len(current_rows) <= 1:
            return
        set_layer_rows_state([row for row in current_rows if row["id"] != row_id])

    return add_layer_row, remove_layer_row, update_layer_row


@app.cell
def _(
    active_model_state,
    filter_rows_state,
    initial_layer_values,
    layer_rows_state,
    model_selector,
    next_filter_id_state,
    next_layer_id_state,
    set_active_model_state,
    set_filter_rows_state,
    set_layer_rows_state,
    set_next_filter_id_state,
    set_next_layer_id_state,
):
    current_model = model_selector.value
    if active_model_state() != current_model:
        set_layer_rows_state(
            [
                {"id": index + 1, "field": field}
                for index, field in enumerate(initial_layer_values)
            ]
        )
        set_next_layer_id_state(len(initial_layer_values) + 1)
        set_filter_rows_state([])
        set_next_filter_id_state(1)
        set_active_model_state(current_model)


@app.cell
def _(
    field_options,
    model_selector,
    token,
):
    import _utils

    all_fields = list(dict.fromkeys(field_options.values()))
    rows = _utils.fetch_plot_data(
        token,
        model_selector.value,
        {
            "values": all_fields,
            "annotate": {"count": {"count": "id"}},
        },
    )
    return all_fields, rows


@app.cell
def _(
    build_filter_options,
    build_plot_rows,
    field_options,
    filter_rows_state,
    layer_rows_state,
    fullscreen,
    mo,
    model_selector,
    remove_layer_row,
    remove_filter_row,
    rows,
    sunburst_figure,
    update_layer_row,
    update_filter_row,
    add_filter_row,
    add_layer_row,
    show_counts_checkbox,
    show_percentages_checkbox,
):
    field_value_to_label = {value: label for label, value in field_options.items()}

    layer_rows_for_ui = layer_rows_state()
    layer_rows_ui = []
    for idx, row in enumerate(layer_rows_for_ui, start=1):
        row_id = row["id"]
        current_field = row.get("field")
        other_layer_fields = {
            existing.get("field")
            for existing in layer_rows_for_ui
            if existing["id"] != row_id and existing.get("field")
        }

        allowed_fields = {
            label: value
            for label, value in field_options.items()
            if value not in other_layer_fields
        }
        if current_field in field_value_to_label:
            allowed_fields.setdefault(field_value_to_label[current_field], current_field)
        if not allowed_fields:
            layer_rows_ui.append(
                mo.md(
                    "_No additional fields available for this layer row. Remove another layer or change the selected class._"
                )
            )
            continue

        current_field_label = (
            field_value_to_label.get(current_field)
            if current_field in field_value_to_label
            else next(iter(allowed_fields.keys()))
        )

        field_selector = mo.ui.dropdown(
            options=allowed_fields,
            value=current_field_label,
            label=f"Layer {idx}",
            searchable=True,
            on_change=lambda value, row_id=row_id: update_layer_row(
                row_id,
                field=value,
            ),
        )

        row_widgets = [field_selector]
        if len(layer_rows_for_ui) > 1:
            row_widgets.append(
                mo.ui.button(
                    label="Remove",
                    kind="warn",
                    on_click=lambda _=None, row_id=row_id: remove_layer_row(row_id),
                )
            )

        layer_rows_ui.append(mo.hstack(row_widgets))

    filter_rows_for_ui = filter_rows_state()
    filter_value_options = build_filter_options(rows, list(field_options.values()))
    rows_ui = []

    for idx, row in enumerate(filter_rows_for_ui, start=1):
        row_id = row["id"]
        current_field = row.get("field")
        other_filter_fields = {
            existing.get("field")
            for existing in filter_rows_for_ui
            if existing["id"] != row_id and existing.get("field")
        }

        allowed_fields = {
            label: value
            for label, value in field_options.items()
            if value not in other_filter_fields
        }
        if current_field in field_value_to_label:
            allowed_fields.setdefault(field_value_to_label[current_field], current_field)
        if not allowed_fields:
            rows_ui.append(
                mo.md(
                    "_No additional fields available for this filter row. Remove another filter or change the selected layers._"
                )
            )
            continue

        current_field_label = (
            field_value_to_label.get(current_field)
            if current_field in field_value_to_label
            else next(iter(allowed_fields.keys()))
        )

        field_selector = mo.ui.dropdown(
            options=allowed_fields,
            value=current_field_label,
            label=f"Filter {idx} field",
            searchable=True,
            on_change=lambda value, row_id=row_id: update_filter_row(
                row_id,
                field=value,
                values=filter_value_options.get(value, []),
            ),
        )

        row_widgets = [
            field_selector,
            mo.ui.button(
                label="Remove",
                kind="warn",
                on_click=lambda _=None, row_id=row_id: remove_filter_row(row_id),
            ),
        ]

        current_options = filter_value_options.get(current_field, [])
        stored_values = row.get("values")
        current_values = stored_values if stored_values is not None else current_options
        current_values = [value for value in current_values if value in current_options]
        if stored_values is None:
            current_values = current_options

        if current_field:
            value_selector = mo.ui.multiselect(
                options=current_options,
                value=current_values,
                label="Include / exclude values",
                full_width=True,
                on_change=lambda value, row_id=row_id: update_filter_row(
                    row_id,
                    values=value,
                ),
            )
            row_widgets.append(value_selector)
        else:
            row_widgets.append(mo.md("_Choose a filter field to show values._"))

        rows_ui.append(mo.vstack([mo.hstack(row_widgets)]))

    layer_add_button = mo.ui.button(label="Add layer", on_click=add_layer_row)
    add_filter_button = mo.ui.button(label="Add Filter", on_click=add_filter_row)
    left_panel = mo.vstack(
        [
            model_selector,
            mo.hstack([show_counts_checkbox, show_percentages_checkbox]),
            mo.md("**Layers**"),
            layer_add_button,
            *(layer_rows_ui or [mo.md("_No layers added yet._")]),
            mo.md("**Filters**"),
            add_filter_button,
            *(rows_ui or [mo.md("_No filters added yet._")]),
        ]
    )
    filter_rows_for_plot = filter_rows_state()
    layer_rows_for_plot = layer_rows_state()
    layer_fields = [
        row["field"]
        for row in layer_rows_for_plot
        if row.get("field")
    ]
    mo.stop(
        not layer_fields,
        mo.md("_No layers selected._"),
    )
    include_values_by_field = {
        row["field"]: set(row.get("values") or [])
        for row in filter_rows_for_plot
        if row.get("field")
    }
    plot_rows = build_plot_rows(
        rows,
        layer_fields,
        include_values_by_field=include_values_by_field,
    )
    if not rows:
        plot_view = mo.md("_No rows returned for the selected class and layers._")
    elif not plot_rows:
        plot_view = mo.md(
            "_No rows remain after applying the selected include/exclude values._"
        )
    else:
        fig = sunburst_figure(
            plot_rows,
            layer_fields,
            fullscreen=fullscreen,
            show_counts=show_counts_checkbox.value,
            show_percentages=show_percentages_checkbox.value,
        )
        if fig is not None:
            svg_download = mo.download(
                lambda fig=fig: fig.to_image(format="svg"),
                filename="custom_sunburst.svg",
                mimetype="image/svg+xml",
                label="Export SVG",
            )
            plot_view = mo.vstack(
                [
                    mo.hstack([svg_download], justify="end"),
                    mo.as_html(fig),
                ],
                gap=0.25,
            )
        else:
            plot_view = mo.md("_No hierarchy could be built for the selected fields._")

    layout = mo.hstack(
        [left_panel, plot_view],
        widths=[0.9, 2.1],
        align="start",
        gap=1.0,
    )
    layout


if __name__ == "__main__":
    app.run()
