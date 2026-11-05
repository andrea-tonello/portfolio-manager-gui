"""Tabs choosing what part of a screen is shown, e.g. Home's open positions or watchlist, filling the row's width."""

import flet as ft

from components.theme import BUTTON_RADIUS

# Height of each tab, and of the rounded fill behind the selected one.
TAB_HEIGHT = 40


def section_tabs(tabs, on_tap) -> ft.Tabs:
    """Return a row of tabs sharing its width, the selected one on a pale rounded fill and in bold; the first is selected.

    `tabs` lists (label, icon) for each tab, icon None for a label alone; an
    icon goes before its label and takes the label's colour. `on_tap(index)`
    is called on each tap, the selected tab's included (e.g. to calculate it
    again), with the tab tapped counted from 0. Setting `disabled` on the
    returned control makes it ignore taps, e.g. while a result is coming.

    The fill is the tab bar's underline made as tall as the tab, with rounded
    corners. A SegmentedButton would only round its outer corners, leaving
    square ones in the middle. Being as large as the tab, the fill lines up
    with the shade a tap or the mouse shows over it.

    Example: section_tabs([("Chart", ft.Icons.AREA_CHART), ("Figures", None)], show)
    calls show(1) when Figures is tapped.
    """
    def label(text, icon):
        """A tab's label: the text alone, or the icon and the text side by side."""
        if icon is None:
            return text
        return ft.Row([ft.Icon(icon, size=20), ft.Text(text)], spacing=8, tight=True,
                      alignment=ft.MainAxisAlignment.CENTER)

    def tapped(e):
        """Note the tab tapped as the selected one, then call on_tap.

        Flet notes it itself only once the fill has finished sliding; a screen
        redrawn before then (e.g. on_tap showing other fields) would otherwise
        slide the fill back to the tab selected before.
        """
        control.selected_index = int(e.data)
        on_tap(control.selected_index)

    control = ft.Tabs(
        length=len(tabs),
        content=ft.TabBar(
            tabs=[ft.Tab(label=label(text, icon), height=TAB_HEIGHT) for text, icon in tabs],
            on_click=tapped,
            scrollable=False,  # the tabs share the row's width
            indicator=ft.UnderlineTabIndicator(border_side=ft.BorderSide(TAB_HEIGHT, ft.Colors.SECONDARY_CONTAINER),
                                               border_radius=BUTTON_RADIUS),
            indicator_thickness=0,  # no room kept under the tabs for an underline
            indicator_size=ft.TabBarIndicatorSize.TAB,
            divider_height=0,
            label_color=ft.Colors.ON_SECONDARY_CONTAINER,
            unselected_label_color=ft.Colors.ON_SURFACE,
            label_text_style=ft.TextStyle(size=14, weight=ft.FontWeight.BOLD),
            unselected_label_text_style=ft.TextStyle(size=14),
            splash_border_radius=BUTTON_RADIUS,
        ),
    )
    return control
