import flet as ft
import flet_charts as fch
import numpy as np


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
    labels = []
    for i in indices:
        dt = dates[i]
        if hasattr(dt, "strftime"):
            text = dt.strftime("%Y-%m-%d")
        else:
            text = str(dt)[:10]
        labels.append(fch.ChartAxisLabel(
            value=i,
            label=ft.Container(
                ft.Text(text, size=9),
                padding=ft.padding.only(top=4),
            ),
        ))
    return labels


def _y_axis_labels(y_min, y_max, num_labels=5):
    """Create evenly-spaced Y axis labels."""
    if y_max == y_min:
        return [fch.ChartAxisLabel(value=y_min, label=ft.Text(f"{y_min:.0f}", size=9))]
    step = (y_max - y_min) / (num_labels - 1)
    labels = []
    for i in range(num_labels):
        val = y_min + i * step
        if abs(val) >= 1000:
            text = f"{val:,.0f}"
        elif abs(val) >= 1:
            text = f"{val:.1f}"
        else:
            text = f"{val:.3f}"
        labels.append(fch.ChartAxisLabel(value=val, label=ft.Text(text, size=9)))
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


def chart_summary(translator, pf_history, min_date_str, dt_str) -> ft.Control:
    """NAV line chart with 4 series. Returns a native Flet control."""
    pf_history = pf_history.dropna().reset_index(drop=True)
    dates = pf_history["Date"].tolist()
    n = len(dates)
    if n == 0:
        return ft.Text("No data")

    series_config = [
        ("NAV", "NAV", ft.Colors.BLUE, 2.5, None),
        ("Valore Titoli", "Securities", ft.Colors.RED, 1.5, [8, 4]),
        ("Liquidita", "Cash", "#1B5E20", 1.5, [8, 4]),
        ("Liquidita Impegnata", "Committed Cash", ft.Colors.LIGHT_GREEN, 1.0, [4, 4]),
    ]

    # Downsample the NAV series for performance
    nav_values = [float(pf_history.iloc[i]["NAV"]) for i in range(n)]
    _, sample_indices = _downsample_series(nav_values, max_points=150)

    all_y = []
    data_series = []
    for col, label, color, width, dash in series_config:
        points = []
        for idx in sample_indices:
            y = float(pf_history.iloc[idx][col])
            points.append(fch.LineChartDataPoint(
                idx, y, show_tooltip=False,
            ))
            all_y.append(y)
        data_series.append(fch.LineChartData(
            points=points,
            color=color,
            stroke_width=width,
            dash_pattern=dash,
            curved=False,
            point=False,
        ))

    y_min = min(all_y)
    y_max = max(all_y)
    y_pad = (y_max - y_min) * 0.05 if y_max != y_min else 1

    chart = fch.LineChart(
        data_series=data_series,
        min_x=0,
        max_x=n - 1,
        min_y=y_min - y_pad,
        max_y=y_max + y_pad,
        expand=True,
        border=ft.Border.all(1, ft.Colors.with_opacity(0.3, ft.Colors.ON_SURFACE)),
        horizontal_grid_lines=fch.ChartGridLines(
            color=ft.Colors.with_opacity(0.15, ft.Colors.ON_SURFACE),
            width=1,
        ),
        bottom_axis=fch.ChartAxis(
            label_size=40,
            labels=_date_axis_labels(dates),
            show_min=False,
            show_max=False,
        ),
        left_axis=fch.ChartAxis(
            label_size=55,
            labels=_y_axis_labels(y_min, y_max),
            show_min=False,
            show_max=False,
        ),
        interactive=False,
    )

    legend = ft.Row([
        ft.Row([
            ft.Container(width=16, height=3, bgcolor=color),
            ft.Text(label, size=11),
        ], spacing=4)
        for _, label, color, _, _ in series_config
    ], spacing=12, wrap=True)

    return ft.Container(
        content=ft.Column([legend, chart], spacing=6, expand=True),
        height=420,
    )


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


def chart_correlation_heatmap(translator, correlation_matrix, start_dt, end_dt) -> ft.Control:
    """Correlation heatmap as a native Flet grid. Returns a Flet control."""
    labels = list(correlation_matrix.columns)
    n = len(labels)

    cell_size = 64
    label_size = 70

    # Build header row: empty corner + column labels
    header_cells = [ft.Container(width=label_size, height=30)]
    for lbl in labels:
        header_cells.append(ft.Container(
            content=ft.Text(lbl, size=9, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
            width=cell_size, height=30,
            alignment=ft.alignment.Alignment.CENTER,
        ))
    header_row = ft.Row(header_cells, spacing=0)

    # Build data rows
    data_rows = []
    for i in range(n):
        row_cells = [ft.Container(
            content=ft.Text(labels[i], size=9, weight=ft.FontWeight.BOLD),
            width=label_size, height=cell_size,
            alignment=ft.alignment.Alignment.CENTER_RIGHT,
            padding=ft.padding.only(right=6),
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
                border=ft.border.all(0.5, ft.Colors.with_opacity(0.2, ft.Colors.BLACK)),
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
        ft.Text(translator.get("analysis.corr.plot1.colorbar"), size=10),
        *scale_containers,
    ], spacing=4)

    return ft.Column([
        ft.Row([ft.Column([header_row, *data_rows], spacing=0)], scroll=ft.ScrollMode.AUTO),
        scale,
    ], spacing=8)


def chart_rolling_correlation(translator, rolling_corr, window, asset1, asset2, start_dt, end_dt) -> ft.Control:
    """Rolling correlation line chart. Returns a native Flet control."""
    rolling_corr = rolling_corr.dropna()
    if rolling_corr.empty:
        return ft.Text("No data")

    # Capture dates before resetting index
    orig_dates = rolling_corr.index.tolist()
    values = rolling_corr.values.tolist()
    n = len(values)

    # Downsample for performance
    sampled_values, sample_indices = _downsample_series(values, max_points=150)

    points = []
    y_vals = []
    for idx in sample_indices:
        y = float(values[idx])
        points.append(fch.LineChartDataPoint(idx, y, show_tooltip=False))
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

    title = translator.get("analysis.corr.plot2.title", window=window, asset1=asset1, asset2=asset2)

    chart = fch.LineChart(
        data_series=[corr_line, zero_line],
        min_x=0,
        max_x=n - 1,
        min_y=max(y_min - y_pad, -1.0),
        max_y=min(y_max + y_pad, 1.0),
        expand=True,
        border=ft.Border.all(1, ft.Colors.with_opacity(0.3, ft.Colors.ON_SURFACE)),
        horizontal_grid_lines=fch.ChartGridLines(
            color=ft.Colors.with_opacity(0.15, ft.Colors.ON_SURFACE),
            width=1,
        ),
        bottom_axis=fch.ChartAxis(
            label_size=40,
            labels=_date_axis_labels(orig_dates),
            show_min=False,
            show_max=False,
        ),
        left_axis=fch.ChartAxis(
            label_size=45,
            labels=_y_axis_labels(
                max(min(y_vals), -1.0),
                min(max(y_vals), 1.0),
                num_labels=5,
            ),
            show_min=False,
            show_max=False,
        ),
        interactive=False,
    )

    legend = ft.Row([
        ft.Row([
            ft.Container(width=16, height=3, bgcolor=ft.Colors.BLUE),
            ft.Text(f"{asset1} / {asset2}", size=11),
        ], spacing=4),
        ft.Row([
            ft.Container(width=16, height=3, bgcolor=ft.Colors.RED),
            ft.Text("Zero", size=11),
        ], spacing=4),
    ], spacing=12, wrap=True)

    return ft.Container(
        content=ft.Column([
            ft.Text(title, size=12, weight=ft.FontWeight.BOLD),
            legend,
            chart,
        ], spacing=6, expand=True),
        height=400,
    )


def chart_drawdown(translator, pf_history, drawdown_series, mdd, start_dt, end_dt) -> ft.Control:
    """Drawdown line chart. Returns a native Flet control."""
    pf_history = pf_history.dropna().reset_index(drop=True)
    drawdown_pct = drawdown_series.reset_index(drop=True) * 100
    dates = pf_history["Date"].tolist()
    n = len(dates)
    if n == 0:
        return ft.Text("No data")

    mdd_pct = mdd * 100

    # Downsample for performance
    dd_values = [float(drawdown_pct.iloc[i]) for i in range(n)]
    _, sample_indices = _downsample_series(dd_values, max_points=150)

    # Drawdown line
    points = []
    y_vals = []
    for idx in sample_indices:
        y = float(drawdown_pct.iloc[idx])
        points.append(fch.LineChartDataPoint(idx, y, show_tooltip=False))
        y_vals.append(y)

    dd_line = fch.LineChartData(
        points=points,
        color=ft.Colors.BLACK,
        stroke_width=1.5,
        curved=False,
        point=False,
    )

    # MDD horizontal reference line
    mdd_line = fch.LineChartData(
        points=[
            fch.LineChartDataPoint(0, mdd_pct, show_tooltip=False),
            fch.LineChartDataPoint(n - 1, mdd_pct, show_tooltip=False),
        ],
        color=ft.Colors.RED,
        stroke_width=2,
        dash_pattern=[8, 4],
        point=False,
    )

    y_min = mdd_pct - 2.5
    y_max = 2.5

    mdd_label = translator.get("analysis.drawdown.plot1.legend", mdd=mdd_pct)

    chart = fch.LineChart(
        data_series=[dd_line, mdd_line],
        min_x=0,
        max_x=n - 1,
        min_y=y_min,
        max_y=y_max,
        expand=True,
        border=ft.Border.all(1, ft.Colors.with_opacity(0.3, ft.Colors.ON_SURFACE)),
        horizontal_grid_lines=fch.ChartGridLines(
            color=ft.Colors.with_opacity(0.15, ft.Colors.ON_SURFACE),
            width=1,
        ),
        bottom_axis=fch.ChartAxis(
            label_size=40,
            labels=_date_axis_labels(dates),
            show_min=False,
            show_max=False,
        ),
        left_axis=fch.ChartAxis(
            label_size=45,
            labels=_y_axis_labels(y_min, y_max),
            show_min=False,
            show_max=False,
        ),
        interactive=False,
    )

    legend = ft.Row([
        ft.Row([
            ft.Container(width=16, height=3, bgcolor=ft.Colors.BLACK),
            ft.Text("Drawdown", size=11),
        ], spacing=4),
        ft.Row([
            ft.Container(width=16, height=3, bgcolor=ft.Colors.RED),
            ft.Text(mdd_label, size=11),
        ], spacing=4),
    ], spacing=12, wrap=True)

    return ft.Container(
        content=ft.Column([legend, chart], spacing=6, expand=True),
        height=420,
    )


def chart_var_mc(translator, scenario_return, var_value, ci, days) -> ft.Control:
    """VaR Monte Carlo histogram. Returns a native Flet BarChart control."""
    scenario_return = np.array(scenario_return)
    if len(scenario_return) == 0:
        return ft.Text("No data")

    # Compute histogram bins (reduced for performance)
    num_bins = 40
    counts, bin_edges = np.histogram(scenario_return, bins=num_bins, density=True)
    bin_width = bin_edges[1] - bin_edges[0]

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
                show_tooltip=False,
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
                padding=ft.padding.only(top=4),
            ),
        ))

    var_legend = translator.get("analysis.var.plot1.legend", ci=ci, var=var_value)

    chart = fch.BarChart(
        groups=groups,
        group_spacing=0,
        max_y=max_count * 1.1,
        min_y=0,
        expand=True,
        border=ft.Border.all(1, ft.Colors.with_opacity(0.3, ft.Colors.ON_SURFACE)),
        horizontal_grid_lines=fch.ChartGridLines(
            color=ft.Colors.with_opacity(0.15, ft.Colors.ON_SURFACE),
            width=1,
        ),
        bottom_axis=fch.ChartAxis(
            label_size=40,
            labels=x_labels,
            show_min=False,
            show_max=False,
        ),
        left_axis=fch.ChartAxis(
            label_size=45,
            show_labels=False,
            show_min=False,
            show_max=False,
        ),
        interactive=False,
    )

    legend = ft.Row([
        ft.Row([
            ft.Container(width=12, height=12, bgcolor="#BDBDBD"),
            ft.Text(translator.get("analysis.var.plot1.xlabel"), size=11),
        ], spacing=4),
        ft.Row([
            ft.Container(width=12, height=12, bgcolor=ft.Colors.RED_300),
            ft.Text(var_legend, size=11),
        ], spacing=4),
    ], spacing=12, wrap=True)

    return ft.Container(
        content=ft.Column([legend, chart], spacing=6, expand=True),
        height=400,
    )
