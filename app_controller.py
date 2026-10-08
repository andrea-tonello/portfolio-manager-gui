"""Top-level navigation: which screen the page shows, and starting the app over.

Screens receive the AppController and call it (app.refresh(), app.show_settings(),
app.restart(), ...) instead of importing navigation functions from the views
package or looking up callbacks in page.data.
"""

import flet as ft

from app_state import AppState
from components.theme import apply_theme
from views import onboarding_view, shell


class AppController:
    """Owns the page's navigation and the current AppState.

    `state` is replaced by a fresh AppState on every restart. `nav_wrapper` is
    the animated container holding the current tab; None means the next
    show_tab rebuilds the whole shell (drawer and navigation bar included).
    """

    def __init__(self, page: ft.Page, base_path: str):
        """Remember the page and the folder holding the app's data (config/ lives inside it)."""
        self.page = page
        self.base_path = base_path
        self.state: AppState | None = None
        self.nav_wrapper: ft.Container | None = None

    def restart(self) -> None:
        """Start over: reload every setting from disk, then show the first setup step still missing, or Home.

        Used at launch and after anything that changes the saved data wholesale
        (switching user, importing a backup, resetting the app).
        """
        page = self.page
        # Pop any pushed views (e.g. Settings) so the rebuild lands on the root
        # view. Otherwise page.appbar / page.controls go to the top (pushed) view
        # while page.end_drawer goes to the root, leaving the drawer disconnected
        # from the visible appbar — menu icon and dialogs silently no-op.
        while len(page.views) > 1:
            page.views.pop()
        page.on_view_pop = None
        page.appbar = None
        page.navigation_bar = None
        # Close any open dialogs
        try:
            page.pop_dialog()
        except Exception:
            pass
        # Clear the stale nav transition wrapper so show_tab creates a fresh one
        self.nav_wrapper = None
        self.state = AppState(base_path=self.base_path)
        self.state.load_config()
        self.state.init_haptic(page)
        apply_theme(page, self.state.theme_mode, self.state.color_seed)

        if self.state.lang_code is None:
            self.show_language_picker()
            return

        if not self.state.users:
            # First launch: offer to restore a backup before creating a user.
            self.show_backup_import()
            return

        if not self.state.brokers:
            self.show_broker_onboarding()
            return

        self.state.ensure_defaults()
        self.state.load_all_accounts()
        self.show_tab(shell.HOME_TAB)

    def show_tab(self, index: int) -> None:
        """Show tab `index`, its position in shell.TABS (Home, Operations, Analysis, Transactions)."""
        shell.show_tab(self, index)

    def refresh(self) -> None:
        """Re-render the tab currently shown, e.g. after the user picks another account in it."""
        self.show_tab(self.state.last_nav_index)

    def show_settings(self) -> None:
        """Open Settings on top of the tabs, or rebuild it if it is already open (e.g. after a language change)."""
        shell.show_settings(self)

    def show_language_picker(self) -> None:
        """Show the first-launch language choice."""
        onboarding_view.show_language_picker(self)

    def show_backup_import(self) -> None:
        """Show the first-launch offer to import a backup, before the user and account screens."""
        onboarding_view.show_backup_import(self)

    def show_user_creation(self, **kwargs) -> None:
        """Show the user-creation screen; see onboarding_view.show_user_creation for the options."""
        onboarding_view.show_user_creation(self, **kwargs)

    def show_broker_onboarding(self, **kwargs) -> None:
        """Show the account setup screen; see onboarding_view.show_broker_onboarding for the options."""
        onboarding_view.show_broker_onboarding(self, **kwargs)
