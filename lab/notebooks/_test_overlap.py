"""Distinct-individual test membership and figures for the test Venn notebook."""

from collections import Counter
from functools import lru_cache
from html import escape
from math import cos, pi, sin


INDIVIDUAL_VALUES = ["id", "samples__tests__test_type_id"]


def individual_test_memberships(rows):
    """Keep untested individuals and collapse repeated tests across samples."""
    memberships = {}
    for row in rows:
        tests = memberships.setdefault(row["id"], set())
        test_type = row.get("samples__tests__test_type_id")
        if test_type is not None:
            tests.add(test_type)
    return memberships


def test_type_options(rows):
    """Use IDs for membership, even when catalog entries share a name."""
    names = Counter(row["name"] for row in rows)
    return {
        f"{row['name']} (#{row['id']})" if names[row["name"]] > 1 else row["name"]: row["id"]
        for row in sorted(rows, key=lambda row: (row["name"].casefold(), row["id"]))
    }


def default_test_types(rows):
    ids = []
    for aliases in ({"wes"}, {"wgs"}, {"rnaseq", "rnasequencing"}):
        for row in rows:
            normalized = "".join(c for c in row["name"].casefold() if c.isalnum())
            if normalized in aliases:
                ids.append(row["id"])
                break
    return ids or [row["id"] for row in rows[:3]]


def overlap_counts(memberships, selected_types):
    """Every individual belongs to one exact region; zero is outside all sets."""
    counts = Counter(
        sum(1 << index for index, test_type in enumerate(selected_types) if test_type in tests)
        for tests in memberships.values()
    )
    if len(selected_types) <= 5:
        return {mask: counts[mask] for mask in range(1 << len(selected_types))}
    return {0: counts[0], **dict(sorted(counts.items()))}


def region_description(mask, labels):
    included = [label for index, label in enumerate(labels) if mask & (1 << index)]
    excluded = [label for index, label in enumerate(labels) if not mask & (1 << index)]
    return (
        "With: " + (", ".join(included) or "none of the selected tests")
        + ("; without: " + ", ".join(excluded) if excluded else "")
    )


def overlap_table(counts, labels):
    return [
        {
            "With tests": ", ".join(label for i, label in enumerate(labels) if mask & (1 << i)) or "None",
            "Without tests": ", ".join(label for i, label in enumerate(labels) if not mask & (1 << i)) or "None",
            "Individuals": count,
        }
        for mask, count in counts.items()
    ]


@lru_cache(maxsize=2)
def ellipse_layout(number):
    """Place each count strictly inside its exact region, away from boundaries."""
    import numpy as np

    if number == 4:
        ellipses = [
            (-0.4, -0.2, 1.7, 0.8, -pi / 4),
            (-0.1, 0.4, 1.7, 0.8, -pi / 4),
            (0.1, 0.4, 1.7, 0.8, pi / 4),
            (0.4, -0.2, 1.7, 0.8, pi / 4),
        ]
    elif number == 5:
        ellipses = [
            (0.5 * cos(i * 2 * pi / 5), 0.5 * sin(i * 2 * pi / 5),
             1.7, 0.9, i * 2 * pi / 5 + pi / 12)
            for i in range(5)
        ]
    else:
        raise ValueError("Complete ellipse layouts support four or five sets")

    x, y = np.meshgrid(np.linspace(-2.3, 2.3, 301), np.linspace(-2.3, 2.3, 301))
    masks = np.zeros(x.shape, dtype=int)
    clearance = np.full(x.shape, np.inf)
    for index, (cx, cy, a, b, angle) in enumerate(ellipses):
        u = (x - cx) * cos(angle) + (y - cy) * sin(angle)
        v = -(x - cx) * sin(angle) + (y - cy) * cos(angle)
        radius = np.sqrt((u / a) ** 2 + (v / b) ** 2)
        masks += (radius < 1) * (1 << index)
        clearance = np.minimum(clearance, abs(radius - 1) * b)
    positions = {}
    for mask in range(1, 1 << number):
        if not np.any(masks == mask):
            raise ValueError(f"Missing region {mask} in ellipse layout")
        point = np.argmax(np.where(masks == mask, clearance, -1))
        positions[mask] = (float(x.flat[point]), float(y.flat[point]))
    return ellipses, positions


def large_overlap_figure(counts, labels, fullscreen=False):
    import plotly.graph_objects as go
    from plotly.colors import qualitative

    number = len(labels)
    if number <= 5:
        ellipses, positions = ellipse_layout(number)
    else:
        # A circle overview remains useful for any number of types, but cannot
        # represent all 2**n regions. Exact counts are supplied by the table.
        ellipses = [
            (0.7 * cos(i * 2 * pi / number), 0.7 * sin(i * 2 * pi / number), 1.35, 1.35, 0)
            for i in range(number)
        ]
        positions = {}

    fig = go.Figure()
    for index, (cx, cy, a, b, angle) in enumerate(ellipses):
        color = qualitative.Safe[index % len(qualitative.Safe)]
        points = [
            (cx + a * cos(t * pi / 90) * cos(angle) - b * sin(t * pi / 90) * sin(angle),
             cy + a * cos(t * pi / 90) * sin(angle) + b * sin(t * pi / 90) * cos(angle))
            for t in range(181)
        ]
        total = sum(count for mask, count in counts.items() if mask & (1 << index))
        fig.add_trace(go.Scatter(
            x=[point[0] for point in points], y=[point[1] for point in points],
            mode="lines", line=dict(color=color, width=2),
            fill="toself", fillcolor=color.replace("rgb", "rgba").replace(")", ", 0.16)"),
            name=f"{escape(labels[index])} ({total:,})", hoverinfo="skip",
        ))
    if positions:
        fig.add_trace(go.Scatter(
            x=[point[0] for point in positions.values()], y=[point[1] for point in positions.values()],
            mode="text", text=[f"{counts[mask]:,}" for mask in positions],
            textfont=dict(size=20 if number == 4 else 16, color="#111827"),
            customdata=[escape(region_description(mask, labels)) for mask in positions],
            hovertemplate="%{customdata}<br>Individuals: %{text}<extra></extra>",
            showlegend=False,
        ))
    fig.add_shape(
        type="rect", x0=-2.5, x1=2.5, y0=-2.9, y1=2.5,
        line=dict(color="#cbd5e1", width=1), layer="below",
    )
    fig.add_annotation(
        x=0, y=-2.65, text=f"None of the selected tests: <b>{counts[0]:,}</b>",
        showarrow=False, font=dict(size=16),
    )
    fig.update_layout(
        template="plotly_white", height=950 if fullscreen else 740,
        margin=dict(t=25, l=10, r=10, b=20),
        legend=dict(orientation="h", y=-0.04, x=0.5, xanchor="center",
                    itemclick=False, itemdoubleclick=False),
        title=dict(
            text="Test totals in legend · exact combinations in table below" if number > 5 else "",
            font=dict(size=14), x=0.5,
        ),
    )
    fig.update_xaxes(visible=False, range=[-2.65, 2.65], fixedrange=True, constrain="domain")
    fig.update_yaxes(visible=False, range=[-3, 2.65], fixedrange=True, scaleanchor="x", scaleratio=1)
    return fig


def overlap_figure(counts, labels, fullscreen=False):
    import plotly.graph_objects as go

    if len(labels) > 3:
        return large_overlap_figure(counts, labels, fullscreen)

    fig = go.Figure()
    fig.update_layout(
        template="plotly_white",
        height=850 if fullscreen else 600,
        margin=dict(t=35, l=20, r=20, b=20),
        showlegend=False,
        font=dict(color="#1f2937"),
    )
    centers = {
        0: [],
        1: [(0, 0)],
        2: [(-0.65, 0), (0.65, 0)],
        3: [(-0.65, 0.4), (0.65, 0.4), (0, -0.65)],
    }[len(labels)]
    positions = {
        0: {},
        1: {1: (0, 0)},
        2: {1: (-1, 0), 2: (1, 0), 3: (0, 0)},
        3: {
            1: (-1.15, 0.65), 2: (1.15, 0.65), 3: (0, 0.85),
            4: (0, -1.25), 5: (-0.65, -0.5), 6: (0.65, -0.5), 7: (0, -0.05),
        },
    }[len(labels)]
    label_positions = {
        0: [], 1: [(0, 1.35)], 2: [(-1, 1.35), (1, 1.35)],
        3: [(-1.1, 1.75), (1.1, 1.75), (0, -1.95)],
    }[len(labels)]
    fig.add_shape(
        type="rect", x0=-2.15, x1=2.15, y0=-2.6, y1=2.05,
        line=dict(color="#cbd5e1", width=1), layer="below",
    )
    colors = [("#4f46e5", "rgba(79,70,229,0.22)"),
              ("#0891b2", "rgba(8,145,178,0.22)"),
              ("#d97706", "rgba(217,119,6,0.22)")]
    for index, (x, y) in enumerate(centers):
        line_color, fill_color = colors[index]
        fig.add_shape(
            type="circle", x0=x-1.15, x1=x+1.15, y0=y-1.15, y1=y+1.15,
            line=dict(color=line_color, width=2), fillcolor=fill_color, layer="below",
        )
        label_x, label_y = label_positions[index]
        total = sum(count for mask, count in counts.items() if mask & (1 << index))
        fig.add_annotation(
            x=label_x, y=label_y, text=f"<b>{escape(labels[index])}</b> ({total:,})",
            showarrow=False, font=dict(size=15, color=line_color),
        )
    if positions:
        fig.add_trace(go.Scatter(
            x=[point[0] for point in positions.values()],
            y=[point[1] for point in positions.values()],
            mode="text", text=[f"{counts[mask]:,}" for mask in positions],
            textfont=dict(size=24),
            customdata=[escape(region_description(mask, labels)) for mask in positions],
            hovertemplate="%{customdata}<br>Individuals: %{text}<extra></extra>",
        ))
    outside_text = "None of the selected tests" if labels else "All individuals (no tests selected)"
    fig.add_annotation(
        x=0, y=-2.35 if labels else 0,
        text=f"{outside_text}: <b>{counts[0]:,}</b>",
        showarrow=False, font=dict(size=16),
    )
    fig.update_xaxes(visible=False, range=[-2.3, 2.3], fixedrange=True, constrain="domain")
    fig.update_yaxes(
        visible=False, range=[-2.75, 2.2], fixedrange=True, scaleanchor="x", scaleratio=1,
    )
    return fig
