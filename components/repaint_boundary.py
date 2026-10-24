import flet as ft


def repaint_boundary(content: ft.Control) -> ft.Control:
    """Return `content` wrapped so Flutter draws it once and then reuses the drawing.

    A scrolling column redraws everything in it on every frame of a scroll, except what 
    sits inside a repaint boundary: that is kept as a finished drawing and just moved. 
    A chart redrawn from scratch at every frame made phones drop frames while scrolling past it.
    """
    return ft.Screenshot(content=content)
