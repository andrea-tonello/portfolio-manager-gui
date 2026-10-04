"""Running a screen's slow work (fetching prices, computing statistics) without freezing the screen."""

import logging

from components.snack import error_message, show_snack
from domain.errors import ValidationError

logger = logging.getLogger(__name__)


def run_in_background(page, translator, work, loading=None):
    """Run `work` in a background thread while `loading` (e.g. a ProgressRing) is shown, then hide it.

    `work` takes no arguments and updates the screen itself. If it raises, the
    error appears in a red snack bar in the user's language (error_message):
    a ValidationError as its translated message, anything else as its own text,
    with the traceback also logged since it may be a bug.

    Example: run_in_background(page, t, save_trade, loading=spinner) shows the
    spinner, saves the trade in a thread, and hides the spinner when done.
    """
    if loading is not None:
        loading.visible = True
        page.update()

    def worker():
        """Run the work in the thread; report any error; always hide the spinner and redraw."""
        try:
            work()
        except Exception as ex:
            if not isinstance(ex, ValidationError):
                logger.exception("Background work failed")
            show_snack(page, error_message(translator, ex), error=True)
        finally:
            if loading is not None:
                loading.visible = False
            page.update()

    page.run_thread(worker)
