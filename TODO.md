
## BACKLOG

- XEON ticker appears when Stocks ETFs is selected
- 0.4.5: aggiorna screenshot Drawer

- [INVESTIGATE] Liquidità impegnata in negativo (BG Saxo)

- [BUG14] in Appendix A
One more question, because of the gain-only rule: what happens to the pending buy fees when an ETF is sold at a loss?
  1. They're included in the loss. The loss grows by the pending buy fees plus the sale fee, and nothing stays pending. This is how costs usually count in a capital loss, so the zainetto ends up with the same total as a sale at a gain, just reported as one bigger loss.
  2. They stay pending until a later sale at a gain. If you sell the whole position at a loss, they're lost for good.
I'd guess 1, but your Fineco statements would show which. 

- [ANSWERED] Can app size be brought further down?
    * No/Not worth it
- [ANSWERED] Can Flet 1.0.3 avoid the focus_chain component (moving between keyboard inputs)?
    * Currently, no. An issue was sent to the Flet team.


## AFTER REFACTOR IS COMPLETE:

- Re-record every transaction



## BACKLOG-BIG

- Region allocation
- Non-chronological insertions
- Bonds
- Bonds ETFs
- iOS UI
    - NavigationBar