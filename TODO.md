
## BACKLOG

- Upgrade to Flet 1.1.0 when available:
    - Fixed FastAPI bug with --android/--web flags is fixed (already fixed in 1.0.5)
    - Support for SVG icons
    - `text_input_action=ft.TextInputAction.NEXT` for TextField
    - `RefreshIndicator` control for Home pull-to-refresh



- "Undo action" button instead of Remove latest transaction
- Select button with bulk delete
- Modernize UI/UX for theme and palette settings
- Tasso USD/EUR
- Wrong month inserted (15-18-2025) --> "Date is missing" snackbar error
- Haptic feedback to charts?
- "Move" operations across the same day?
- flet's DataTable2



- XEON ticker appears when Stocks ETFs is selected

- [INVESTIGATE] Liquidità impegnata in negativo (BG Saxo)


- [BUG14] in Appendix A
One more question, because of the gain-only rule: what happens to the pending buy fees when an ETF is sold at a loss?
  1. They're included in the loss. The loss grows by the pending buy fees plus the sale fee, and nothing stays pending. This is how costs usually count in a capital loss, so the zainetto ends up with the same total as a sale at a gain, just reported as one bigger loss.
  2. They stay pending until a later sale at a gain. If you sell the whole position at a loss, they're lost for good.
I'd guess 1, but your Fineco statements would show which. 



## AFTER REFACTOR IS COMPLETE:

- Re-record every transaction



## BACKLOG-BIG

- Region allocation
- Bonds
- Bonds ETFs
- iOS UI
    - NavigationBar