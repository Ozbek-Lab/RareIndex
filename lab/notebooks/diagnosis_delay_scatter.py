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
    from datetime import date, datetime

    FIELD_LABELS = {
        "sex": "Sex",
        "is_index": "Index status",
        "is_affected": "Affected status",
    }

    def parse_date(value):
        if not value:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value).strip()
        if not text:
            return None
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None

    def add_months(start_date, months):
        month_index = start_date.month - 1 + int(months)
        year = start_date.year + month_index // 12
        month = month_index % 12 + 1
        month_lengths = [
            31,
            29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
            31,
            30,
            31,
            30,
            31,
            31,
            30,
            31,
            30,
            31,
        ]
        day = min(start_date.day, month_lengths[month - 1])
        return date(year, month, day)

    def months_between(start_date, end_date):
        months = (end_date.year - start_date.year) * 12 + end_date.month - start_date.month
        if end_date.day < start_date.day:
            months -= 1
        return months

    def label_bool(value, true_label, false_label):
        if value is True:
            return true_label
        if value is False:
            return false_label
        return "Unknown"

    def display_value(value):
        if value in (None, ""):
            return "Unknown"
        return str(value).strip().title()

    def truncate(value, limit=80):
        text = str(value or "").strip()
        if len(text) <= limit:
            return text or "No diagnosis text"
        return text[: limit - 1].rstrip() + "..."

    def build_delay_rows(api_rows, include_negative=False):
        rows = []
        skipped = {
            "missing_birth_date": 0,
            "missing_diagnosis_date": 0,
            "missing_onset_months": 0,
            "negative_delay": 0,
        }

        for row in api_rows:
            birth_date = parse_date(row.get("birth_date"))
            diagnosis_date = parse_date(row.get("diagnosis_date"))
            onset_months = row.get("age_of_onset_in_months")

            if birth_date is None:
                skipped["missing_birth_date"] += 1
                continue
            if diagnosis_date is None:
                skipped["missing_diagnosis_date"] += 1
                continue
            if onset_months in (None, ""):
                skipped["missing_onset_months"] += 1
                continue

            try:
                onset_months = int(onset_months)
            except (TypeError, ValueError):
                skipped["missing_onset_months"] += 1
                continue

            age_at_diagnosis_months = months_between(birth_date, diagnosis_date)
            delay_months = age_at_diagnosis_months - onset_months
            if delay_months < 0:
                skipped["negative_delay"] += 1
                if not include_negative:
                    continue

            estimated_onset_date = add_months(birth_date, onset_months)
            rows.append(
                {
                    "id": row.get("id"),
                    "birth_date": birth_date,
                    "diagnosis_date": diagnosis_date,
                    "estimated_onset_date": estimated_onset_date,
                    "age_of_onset": row.get("age_of_onset") or "",
                    "age_of_onset_months": onset_months,
                    "age_at_diagnosis_months": age_at_diagnosis_months,
                    "delay_months": delay_months,
                    "sex": display_value(row.get("sex")),
                    "is_index": label_bool(row.get("is_index"), "Index", "Not index"),
                    "is_affected": label_bool(row.get("is_affected"), "Affected", "Unaffected"),
                    "diagnosis": truncate(row.get("diagnosis")),
                }
            )

        return rows, skipped

    def unit_value(months, unit):
        if unit == "years":
            return round(months / 12, 2)
        return months

    return FIELD_LABELS, build_delay_rows, unit_value


@app.cell
def _(mo):
    import _utils

    qp = mo.query_params()
    default_x_axis = str(_utils._qp_get(qp, "x_axis", "diagnosis_date")).strip()
    default_unit = str(_utils._qp_get(qp, "unit", "years")).strip()
    default_color = str(_utils._qp_get(qp, "color", "is_affected")).strip()
    default_include_negative = str(
        _utils._qp_get(qp, "include_negative", "")
    ).strip().lower() in {"1", "true", "yes", "on"}
    fullscreen = str(_utils._qp_get(qp, "fullscreen", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    return (
        default_color,
        default_include_negative,
        default_unit,
        default_x_axis,
        fullscreen,
    )


@app.cell
def _(default_color, default_include_negative, default_unit, default_x_axis, mo):
    x_axis_options = {
        "Diagnosis date": "diagnosis_date",
        "Age at onset": "age_of_onset_months",
        "Age at diagnosis": "age_at_diagnosis_months",
    }
    unit_options = {"Years": "years", "Months": "months"}
    color_options = {
        "Affected status": "is_affected",
        "Index status": "is_index",
        "Sex": "sex",
    }
    x_axis_default_label = next(
        (
            label
            for label, value in x_axis_options.items()
            if value == default_x_axis
        ),
        "Diagnosis date",
    )
    unit_default_label = next(
        (label for label, value in unit_options.items() if value == default_unit),
        "Years",
    )
    color_default_label = next(
        (label for label, value in color_options.items() if value == default_color),
        "Affected status",
    )

    x_axis = mo.ui.dropdown(
        options=x_axis_options,
        value=x_axis_default_label,
        label="X-axis",
    )
    unit = mo.ui.dropdown(
        options=unit_options,
        value=unit_default_label,
        label="Duration unit",
    )
    color_by = mo.ui.dropdown(
        options=color_options,
        value=color_default_label,
        label="Color by",
    )
    include_negative = mo.ui.checkbox(
        value=default_include_negative,
        label="Show diagnosis dates before estimated onset",
    )
    return color_by, include_negative, unit, x_axis


@app.cell
def _(token):
    import _utils

    rows = _utils.fetch_plot_data(
        token,
        "Individual",
        {
            "values": [
                "id",
                "birth_date",
                "diagnosis_date",
                "age_of_onset",
                "age_of_onset_in_months",
                "sex",
                "is_index",
                "is_affected",
                "diagnosis",
            ],
        },
    )
    return (rows,)


@app.cell
def _(build_delay_rows, include_negative, rows):
    delay_rows, skipped_rows = build_delay_rows(
        rows,
        include_negative=include_negative.value,
    )
    return delay_rows, skipped_rows


@app.cell
def _(FIELD_LABELS, color_by, delay_rows, fullscreen, unit, unit_value, x_axis):
    import plotly.graph_objects as go

    def scatter_figure():
        if not delay_rows:
            return None

        selected_unit = unit.value
        unit_label = "years" if selected_unit == "years" else "months"
        x_field = x_axis.value
        color_field = color_by.value
        categories = sorted({row[color_field] for row in delay_rows})
        title_by_x = {
            "diagnosis_date": "Diagnosis date",
            "age_of_onset_months": f"Age at onset ({unit_label})",
            "age_at_diagnosis_months": f"Age at diagnosis ({unit_label})",
        }

        fig = go.Figure()
        for category in categories:
            category_rows = [row for row in delay_rows if row[color_field] == category]
            if x_field == "diagnosis_date":
                x_values = [row["diagnosis_date"] for row in category_rows]
            else:
                x_values = [
                    unit_value(row[x_field], selected_unit)
                    for row in category_rows
                ]

            y_values = [
                unit_value(row["delay_months"], selected_unit)
                for row in category_rows
            ]
            customdata = [
                [
                    row["id"],
                    row["age_of_onset"] or "Not recorded",
                    unit_value(row["age_of_onset_months"], selected_unit),
                    row["estimated_onset_date"].isoformat(),
                    row["diagnosis_date"].isoformat(),
                    unit_value(row["age_at_diagnosis_months"], selected_unit),
                    row["diagnosis"],
                ]
                for row in category_rows
            ]
            marker_sizes = [13 if row["is_index"] == "Index" else 9 for row in category_rows]

            fig.add_trace(
                go.Scatter(
                    x=x_values,
                    y=y_values,
                    mode="markers",
                    name=str(category),
                    customdata=customdata,
                    marker={
                        "size": marker_sizes,
                        "opacity": 0.82,
                        "line": {"color": "rgba(17, 24, 39, 0.35)", "width": 1},
                    },
                    hovertemplate=(
                        "<b>Individual %{customdata[0]}</b><br>"
                        "Delay: %{y} "
                        + unit_label
                        + "<br>"
                        "Age of onset: %{customdata[1]} (%{customdata[2]} "
                        + unit_label
                        + ")<br>"
                        "Estimated onset date: %{customdata[3]}<br>"
                        "Diagnosis date: %{customdata[4]}<br>"
                        "Age at diagnosis: %{customdata[5]} "
                        + unit_label
                        + "<br>"
                        "Diagnosis: %{customdata[6]}"
                        "<extra></extra>"
                    ),
                )
            )

        fig.add_hline(
            y=0,
            line_dash="dot",
            line_color="rgba(107, 114, 128, 0.75)",
            annotation_text="diagnosis before onset",
            annotation_position="bottom right",
        )
        fig.update_layout(
            autosize=True,
            height=1100 if fullscreen else 780,
            margin={"t": 20, "l": 10, "r": 10, "b": 10},
            xaxis_title=title_by_x.get(x_field, "X"),
            yaxis_title=f"Time from onset to diagnosis ({unit_label})",
            legend_title_text=FIELD_LABELS.get(color_field, color_field),
            hovermode="closest",
        )
        return fig

    figure = scatter_figure()
    return (figure,)


@app.cell
def _(delay_rows, include_negative, skipped_rows, unit, unit_value):
    if delay_rows:
        delays = [row["delay_months"] for row in delay_rows]
        median_delay = sorted(delays)[len(delays) // 2]
        max_delay = max(delays)
        min_delay = min(delays)
    else:
        median_delay = max_delay = min_delay = 0

    negative_label = (
        "Negative delays shown"
        if include_negative.value
        else "Negative delays hidden"
    )
    summary = {
        "Plotted individuals": f"{len(delay_rows):,}",
        "Median delay": f"{unit_value(median_delay, unit.value):,} {unit.value}",
        "Range": (
            f"{unit_value(min_delay, unit.value):,} to "
            f"{unit_value(max_delay, unit.value):,} {unit.value}"
        ),
        "Missing birth date": f"{skipped_rows['missing_birth_date']:,}",
        "Missing diagnosis date": f"{skipped_rows['missing_diagnosis_date']:,}",
        "Missing onset months": f"{skipped_rows['missing_onset_months']:,}",
        negative_label: f"{skipped_rows['negative_delay']:,}",
    }
    return (summary,)


@app.cell
def _(color_by, figure, include_negative, mo, summary, unit, x_axis):
    controls = mo.hstack(
        [x_axis, unit, color_by, include_negative],
        justify="start",
        wrap=True,
        gap=1,
    )
    summary_md = " · ".join(
        f"**{label}:** {value}" for label, value in summary.items()
    )

    if figure is None:
        output = mo.md(
            "No individuals have enough data to calculate diagnosis delay. "
            "The plot needs `birth_date`, `age_of_onset_in_months`, and `diagnosis_date`."
        )
    else:
        output = mo.as_html(figure)

    mo.vstack(
        [
            mo.md("### Time From Symptom Onset to Diagnosis"),
            controls,
            mo.md(summary_md),
            output,
        ]
    )
    return


if __name__ == "__main__":
    app.run()
