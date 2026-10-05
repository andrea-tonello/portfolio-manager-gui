"""The charts of the Analysis tab, built as native Flet controls.

Each chart_* function takes the translator first and returns one control: a
white card holding a legend and the chart, or a short text when there is
nothing to draw. The helpers below give every chart the same card, axes,
grid, tooltips and legend style.
"""

import flet as ft
import flet_charts as fch
import numpy as np

from utils.columns import PRODUCT_LOCALE_KEYS
from utils.formatting import fmt_eur


def _fmt_date(dt):
    """Write a date as YYYY-MM-DD, whether it is a date/Timestamp or already text."""
    return dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)[:10]


def _no_data(t):
    """The text shown in place of a chart with nothing to draw."""
    return ft.Text(t.get("analysis.charts.no_data"))


def _chart_card(*children, spacing=6):
    """The white rounded card, 320 high with a light shadow, that holds every chart and its legend."""
    return ft.Container(
        content=ft.Column(list(children), spacing=spacing, expand=True),
        bgcolor=ft.Colors.WHITE,
        border_radius=12,
        padding=8,
        height=320,
        shadow=ft.BoxShadow(
            spread_radius=1, blur_radius=3,
            color=ft.Colors.with_opacity(0.1, ft.Colors.BLACK),
        ),
    )


def _legend(entries, gap="   "):
    """A one-line legend: for each (color, label), a coloured square and the label, entries `gap` apart.

    An entry can name another symbol as a third item, e.g. (RED, "Max", "●"), and
    a colour of None shows the label alone. Example: [(BLUE, "NAV"), (RED, "Cash")]
    reads "■ NAV   ■ Cash" with blue and red squares.
    """
    spans = []
    for i, (color, label, *symbol) in enumerate(entries):
        if color is not None:
            marker = symbol[0] if symbol else "■"
            # A dot looks smaller than a square of the same size, so it is drawn bigger.
            spans.append(ft.TextSpan(marker + " ", style=ft.TextStyle(color=color, size=14 if marker == "●" else 10)))
        spans.append(ft.TextSpan(label + ("" if i == len(entries) - 1 else gap),
                                 style=ft.TextStyle(color=ft.Colors.BLACK, size=10)))
    return ft.Text(spans=spans)


def _chart_frame():
    """Settings shared by the line and bar charts: they fill the card, with a thin border, grid lines and tooltips."""
    return {
        "expand": True,
        "border": ft.Border.all(1, ft.Colors.with_opacity(0.3, ft.Colors.ON_SURFACE)),
        "horizontal_grid_lines": fch.ChartGridLines(
            color=ft.Colors.with_opacity(0.15, ft.Colors.ON_SURFACE),
            width=1,
        ),
        "interactive": True,
    }


def _tooltip(kind):
    """The grey tooltip box every chart uses; `kind` is fch.LineChartTooltip or fch.BarChartTooltip."""
    return kind(
        bgcolor="#E0E0E0",
        border_radius=8,
        padding=ft.Padding.all(8),
        max_width=160,
        fit_inside_horizontally=True,
        fit_inside_vertically=True,
    )


def _line_chart(data_series, dates, min_y, max_y, y_labels):
    """A line chart with one point per date (x = the date's position), dates along the bottom and `y_labels` on the left."""
    return fch.LineChart(
        data_series=data_series,
        min_x=0,
        max_x=len(dates) - 1,
        min_y=min_y,
        max_y=max_y,
        bottom_axis=fch.ChartAxis(
            label_size=0,
            labels=_date_axis_labels(dates),
            show_min=False,
            show_max=False,
        ),
        left_axis=fch.ChartAxis(
            label_size=0,
            labels=y_labels,
            show_min=False,
            show_max=False,
        ),
        tooltip=_tooltip(fch.LineChartTooltip),
        **_chart_frame(),
    )


def _date_axis_labels(dates, num_labels=6):
    """Create evenly-spaced ChartAxisLabels from a list of dates."""
    n = len(dates)
    if n == 0:
        return []
    if n <= num_labels:
        indices = list(range(n))
    else:
        step = (n - 1) / (num_labels - 1)
        indices = [int(round(i * step)) for i in range(num_labels)]
    return [fch.ChartAxisLabel(value=i, label=_fmt_date(dates[i])) for i in indices]


def _y_axis_labels(y_min, y_max, num_labels=5, suffix=""):
    """Create evenly-spaced Y axis labels."""
    if y_max == y_min:
        return [fch.ChartAxisLabel(value=y_min, label=f"{y_min:.0f}{suffix}")]
    step = (y_max - y_min) / (num_labels - 1)
    labels = []
    for i in range(num_labels):
        val = y_min + i * step
        if abs(val) >= 1000:
            text = f"{val:,.0f}{suffix}"
        elif abs(val) >= 1:
            text = f"{val:.1f}{suffix}"
        else:
            text = f"{val:.3f}{suffix}"
        labels.append(fch.ChartAxisLabel(value=val, label=text))
    return labels


def _downsample_series(data, max_points=200):
    """Downsample data using Largest Triangle Three Buckets algorithm for performance.

    Keeps first, last, and most visually significant points in between.
    """
    n = len(data)
    if n <= max_points:
        return data, list(range(n))

    # Always keep first and last
    sampled = [data[0]]
    sampled_indices = [0]

    bucket_size = (n - 2) / (max_points - 2)

    a = 0  # Initially point a is the first point

    for i in range(max_points - 2):
        # Calculate point average for next bucket
        avg_x = 0
        avg_y = 0
        avg_range_start = int((i + 1) * bucket_size) + 1
        avg_range_end = int((i + 2) * bucket_size) + 1
        avg_range_end = min(avg_range_end, n)
        avg_range_length = avg_range_end - avg_range_start

        if avg_range_length > 0:
            for j in range(avg_range_start, avg_range_end):
                avg_x += j
                avg_y += data[j]
            avg_x /= avg_range_length
            avg_y /= avg_range_length
        else:
            avg_x = avg_range_start
            avg_y = data[avg_range_start] if avg_range_start < n else data[-1]

        # Get the range for this bucket
        range_offs = int(i * bucket_size) + 1
        range_to = int((i + 1) * bucket_size) + 1

        point_a_x = a
        point_a_y = data[a]

        max_area = -1
        max_area_point = range_offs

        for j in range(range_offs, min(range_to, n)):
            # Calculate triangle area
            area = abs((point_a_x - avg_x) * (data[j] - point_a_y) -
                      (point_a_x - j) * (avg_y - point_a_y))
            if area > max_area:
                max_area = area
                max_area_point = j

        sampled.append(data[max_area_point])
        sampled_indices.append(max_area_point)
        a = max_area_point

    # Always add last point
    sampled.append(data[-1])
    sampled_indices.append(n - 1)

    return sampled, sampled_indices


def chart_summary(translator, pf_history) -> ft.Control:
    """NAV line chart with 4 series. Returns a native Flet control."""
    pf_history = pf_history.dropna().reset_index(drop=True)
    dates = pf_history["Date"].tolist()
    n = len(dates)
    if n == 0:
        return _no_data(translator)

    series_config = [
        ("nav", translator.get("analysis.charts.nav"), ft.Colors.BLUE, 2.5, None),
        ("assets_value", translator.get("analysis.charts.securities"), ft.Colors.RED, 1.5, [8, 4]),
        ("cash", translator.get("analysis.charts.cash"), "#1B5E20", 1.5, [8, 4]),
        ("committed_cash", translator.get("analysis.charts.committed_cash"), ft.Colors.LIGHT_GREEN, 1.0, [4, 4]),
    ]

    # Downsample the NAV series for performance
    nav_values = [float(pf_history.iloc[i]["nav"]) for i in range(n)]
    _, sample_indices = _downsample_series(nav_values, max_points=150)

    all_y = []
    data_series = []
    first_series = True
    for col, label, color, width, dash in series_config:
        points = []
        for idx in sample_indices:
            y = float(pf_history.iloc[idx][col])
            if first_series:
                tip = fch.LineChartDataPointTooltip(
                    text=f"{_fmt_date(dates[idx])}\n{label}: {y:,.0f}",
                    text_style=ft.TextStyle(size=10),
                )
            else:
                tip = fch.LineChartDataPointTooltip(
                    text=f"{label}: {y:,.0f}",
                    text_style=ft.TextStyle(size=10),
                )
            points.append(fch.LineChartDataPoint(idx, y, tooltip=tip))
            all_y.append(y)
        data_series.append(fch.LineChartData(
            points=points,
            color=color,
            stroke_width=width,
            dash_pattern=dash,
            curved=False,
            point=False,
        ))
        first_series = False

    y_min = min(all_y)
    y_max = max(all_y)
    y_pad = (y_max - y_min) * 0.05 if y_max != y_min else 1

    chart = _line_chart(data_series, dates, y_min - y_pad, y_max + y_pad, _y_axis_labels(y_min, y_max))
    legend = _legend([(color, label) for _, label, color, _, _ in series_config])
    return _chart_card(legend, chart)


def _corr_color(value: float) -> str:
    """Map a correlation value (-1 to 1) to a coolwarm-like color."""
    # Clamp
    v = max(-1.0, min(1.0, value))
    # Interpolate: -1 = blue (66,133,244), 0 = white, +1 = red (234,67,53)
    if v >= 0:
        r = int(255 - (255 - 234) * v)
        g = int(255 - (255 - 67) * v)
        b = int(255 - (255 - 53) * v)
    else:
        a = -v
        r = int(255 - (255 - 66) * a)
        g = int(255 - (255 - 133) * a)
        b = int(255 - (255 - 244) * a)
    return f"#{r:02x}{g:02x}{b:02x}"


def chart_correlation_heatmap(translator, correlation_matrix) -> ft.Control:
    """Correlation heatmap as a native Flet grid. Returns a Flet control."""
    labels = list(correlation_matrix.columns)
    n = len(labels)

    cell_size = 64
    label_size = 70

    # Build header row: empty corner + column labels
    header_cells = [ft.Container(width=label_size, height=30)]
    for lbl in labels:
        header_cells.append(ft.Container(
            content=ft.Text(lbl, size=9, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER, color=ft.Colors.BLACK),
            width=cell_size, height=30,
            alignment=ft.alignment.Alignment.CENTER,
        ))
    header_row = ft.Row(header_cells, spacing=0)

    # Build data rows
    data_rows = []
    for i in range(n):
        row_cells = [ft.Container(
            content=ft.Text(labels[i], size=9, weight=ft.FontWeight.BOLD, color=ft.Colors.BLACK),
            width=label_size, height=cell_size,
            alignment=ft.alignment.Alignment.CENTER_RIGHT,
            padding=ft.Padding.only(right=6),
        )]
        for j in range(n):
            val = float(correlation_matrix.iloc[i, j])
            bg = _corr_color(val)
            row_cells.append(ft.Container(
                content=ft.Text(f"{val:.3f}", size=11, color=ft.Colors.BLACK,
                                text_align=ft.TextAlign.CENTER),
                width=cell_size, height=cell_size,
                bgcolor=bg,
                alignment=ft.alignment.Alignment.CENTER,
                border=ft.Border.all(0.5, ft.Colors.with_opacity(0.2, ft.Colors.BLACK)),
            ))
        data_rows.append(ft.Row(row_cells, spacing=0))

    # Color scale legend
    scale_containers = []
    for v in [-1.0, -0.5, 0.0, 0.5, 1.0]:
        scale_containers.append(ft.Container(
            content=ft.Text(f"{v:.1f}", size=8, color=ft.Colors.BLACK, text_align=ft.TextAlign.CENTER),
            width=36, height=18, bgcolor=_corr_color(v),
            alignment=ft.alignment.Alignment.CENTER,
        ))
    scale = ft.Row([
        ft.Text(translator.get("analysis.corr.plot_title_simple"), size=10, color=ft.Colors.BLACK),
        *scale_containers,
    ], spacing=4)

    grid = ft.Row([ft.Column([header_row, *data_rows], spacing=0)], scroll=ft.ScrollMode.AUTO)
    return _chart_card(grid, scale, spacing=8)


def chart_rolling_correlation(translator, rolling_corr, window, asset1, asset2) -> ft.Control:
    """Rolling correlation line chart. Returns a native Flet control."""
    rolling_corr = rolling_corr.dropna()
    if rolling_corr.empty:
        return ft.Text(translator.get("analysis.corr.rolling_nodata"), size=14)

    # Capture dates before resetting index
    orig_dates = rolling_corr.index.tolist()
    values = rolling_corr.values.tolist()
    n = len(values)

    # Downsample for performance
    _, sample_indices = _downsample_series(values, max_points=150)

    points = []
    y_vals = []
    corr_label = translator.get("analysis.charts.corr")
    for idx in sample_indices:
        y = float(values[idx])
        points.append(fch.LineChartDataPoint(
            idx, y,
            tooltip=fch.LineChartDataPointTooltip(
                text=f"{_fmt_date(orig_dates[idx])}\n{corr_label}: {y:.3f}",
                text_style=ft.TextStyle(size=10),
            ),
        ))
        y_vals.append(y)

    # Main correlation line
    corr_line = fch.LineChartData(
        points=points,
        color=ft.Colors.BLUE,
        stroke_width=1.5,
        curved=False,
        point=False,
    )

    # Zero reference line
    zero_line = fch.LineChartData(
        points=[
            fch.LineChartDataPoint(0, 0, show_tooltip=False),
            fch.LineChartDataPoint(n - 1, 0, show_tooltip=False),
        ],
        color=ft.Colors.RED,
        stroke_width=1,
        dash_pattern=[6, 3],
        point=False,
    )

    y_min = min(y_vals + [0])
    y_max = max(y_vals + [0])
    y_pad = max((y_max - y_min) * 0.1, 0.05)

    title = translator.get("analysis.corr.plot_title_rolling", window=window, asset1=asset1, asset2=asset2)

    chart = _line_chart(
        [corr_line, zero_line], orig_dates, max(y_min - y_pad, -1.0), min(y_max + y_pad, 1.0),
        _y_axis_labels(max(min(y_vals), -1.0), min(max(y_vals), 1.0), num_labels=5),
    )
    legend = _legend([
        (ft.Colors.BLUE, f"{asset1} / {asset2}"),
        (ft.Colors.RED, translator.get("analysis.charts.zero")),
    ])
    return _chart_card(ft.Text(title, size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.BLACK), legend, chart)


def chart_drawdown(translator, pf_history, drawdown_series, mdd) -> ft.Control:
    """Drawdown line chart. Returns a native Flet control."""
    pf_history = pf_history.dropna().reset_index(drop=True)
    drawdown_pct = drawdown_series.reset_index(drop=True) * 100
    dates = pf_history["Date"].tolist()
    n = len(dates)
    if n == 0:
        return _no_data(translator)

    mdd_pct = mdd * 100

    # Downsample for performance
    dd_values = [float(drawdown_pct.iloc[i]) for i in range(n)]
    mdd_idx = int(drawdown_pct.idxmin())
    _, sample_indices = _downsample_series(dd_values, max_points=150)
    if mdd_idx not in sample_indices:
        sample_indices.append(mdd_idx)
        sample_indices.sort()

    # Drawdown line
    points = []
    y_vals = []
    for idx in sample_indices:
        y = float(drawdown_pct.iloc[idx])
        pt_marker = (
            fch.ChartCirclePoint(color=ft.Colors.RED, radius=5)
            if idx == mdd_idx else False
        )
        points.append(fch.LineChartDataPoint(
            idx, y,
            point=pt_marker,
            tooltip=fch.LineChartDataPointTooltip(
                text=f"{_fmt_date(dates[idx])}\nDD: {y:.1f}%",
                text_style=ft.TextStyle(size=10),
            ),
        ))
        y_vals.append(y)

    dd_line = fch.LineChartData(
        points=points,
        color=ft.Colors.BLACK,
        stroke_width=1.5,
        curved=False,
        point=False,
    )

    # Zero reference line
    zero_line = fch.LineChartData(
        points=[
            fch.LineChartDataPoint(0, 0, show_tooltip=False),
            fch.LineChartDataPoint(n - 1, 0, show_tooltip=False),
        ],
        color=ft.Colors.with_opacity(0.5, ft.Colors.GREY),
        stroke_width=1,
        dash_pattern=[6, 4],
        point=False,
    )

    y_min = mdd_pct - 2.5
    y_max = 2.5

    chart = _line_chart([dd_line, zero_line], dates, y_min, y_max, _y_axis_labels(y_min, y_max, suffix="%"))
    legend = _legend([
        (ft.Colors.BLACK, translator.get("analysis.charts.drawdown")),
        (ft.Colors.with_opacity(0.5, ft.Colors.GREY), translator.get("analysis.charts.zero")),
        (ft.Colors.RED, translator.get("analysis.drawdown.legend", mdd=mdd_pct), "●"),
    ])
    return _chart_card(legend, chart)


def chart_var_mc(translator, scenario_return, var_value, ci) -> ft.Control:
    """VaR Monte Carlo histogram. Returns a native Flet BarChart control."""
    scenario_return = np.array(scenario_return)
    if len(scenario_return) == 0:
        return _no_data(translator)

    # Compute histogram bins (reduced for performance)
    num_bins = 40
    counts, bin_edges = np.histogram(scenario_return, bins=num_bins, density=True)

    # Create bar groups
    groups = []
    max_count = float(counts.max()) if len(counts) > 0 else 1
    var_threshold = -var_value

    for i, count in enumerate(counts):
        bin_center = (bin_edges[i] + bin_edges[i + 1]) / 2
        # Color bars at or below -VaR red, rest gray
        color = ft.Colors.RED_300 if bin_center <= var_threshold else "#BDBDBD"
        groups.append(fch.BarChartGroup(
            x=i,
            rods=[fch.BarChartRod(
                from_y=0,
                to_y=float(count),
                width=max(2, 400 / num_bins),
                color=color,
                border_radius=0,
                tooltip=fch.BarChartRodTooltip(
                    text=fmt_eur(bin_center),
                    text_style=ft.TextStyle(size=10, color=ft.Colors.BLACK),
                ),
            )],
        ))

    # X-axis: show ~5 evenly spaced value labels
    num_x_labels = 5
    x_step = max(1, num_bins // (num_x_labels - 1))
    x_labels = []
    for i in range(0, num_bins, x_step):
        val = (bin_edges[i] + bin_edges[i + 1]) / 2
        x_labels.append(fch.ChartAxisLabel(
            value=i,
            label=ft.Container(
                ft.Text(f"{val:,.0f}", size=9),
                padding=ft.Padding.only(top=4),
            ),
        ))

    chart = fch.BarChart(
        groups=groups,
        group_spacing=0,
        max_y=max_count * 1.1,
        min_y=0,
        bottom_axis=fch.ChartAxis(
            label_size=20,
            labels=x_labels,
            show_min=False,
            show_max=False,
        ),
        left_axis=fch.ChartAxis(
            label_size=0,
            labels=_y_axis_labels(0, max_count * 1.1, num_labels=3),
            show_min=False,
            show_max=False,
        ),
        tooltip=_tooltip(fch.BarChartTooltip),
        **_chart_frame(),
    )

    legend = _legend([
        (None, translator.get("analysis.var.axes")),
        (ft.Colors.RED_300, translator.get("analysis.var.legend", ci=ci, var=var_value)),
    ], gap="       ")
    return _chart_card(legend, chart)


_ALLOC_COLORS = {
    "Stock": ft.Colors.BLUE,
    "ETF-S": ft.Colors.LIGHT_BLUE_200,
    # Placeholder for the planned individual bonds (TODO.md): no product is stored
    # as "Bond" yet. When bonds are added, make sure their product code matches
    # this key (and add a PRODUCT_LOCALE_KEYS entry), or the slice turns grey.
    "Bond": ft.Colors.AMBER,
    "ETF-B": ft.Colors.YELLOW,
    "ETF-M": ft.Colors.LIGHT_GREEN,
    "Cash": ft.Colors.BLUE_GREY,
}


def chart_allocation(translator, allocation):
    """Build a PieChart from an allocation dict {product_type: value}."""
    total = sum(allocation.values())
    if total <= 0:
        return _no_data(translator)

    sections = []
    legend_items = []
    for i, (product, value) in enumerate(sorted(allocation.items(), key=lambda x: -x[1])):
        pct = value / total * 100
        color = _ALLOC_COLORS.get(product, ft.Colors.GREY)
        locale_key = PRODUCT_LOCALE_KEYS.get(product)
        label = translator.get(locale_key).strip() if locale_key else product
        sections.append(fch.PieChartSection(
            value=value,
            title=f"{pct:.1f}%",
            title_style=ft.TextStyle(size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
            title_position=0.5,
            color=color,
            radius=110,
        ))
        legend_items.append(
            ft.Row([
                ft.Container(width=14, height=14, bgcolor=color, border_radius=3),
                ft.Text(f"{label}  ({pct:.1f}%)", size=12),
            ], spacing=6)
        )

    pie = fch.PieChart(
        sections=sections,
        sections_space=2,
        center_space_radius=0,
        width=250,
        height=250,
    )

    legend = ft.Column(legend_items, spacing=4)

    return ft.Container(
        ft.Column([
            ft.Row([pie], alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(height=10),
            legend,
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
        padding=15,
    )
