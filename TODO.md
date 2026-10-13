
## BACKLOG

- Make the ticker suggestion overlay an actual overlay (instead of shifting down the content below it)

- XEON ticker appears when Stocks ETFs is selected
- [TABLET] Reduce account dropdown width in each of the 4 main views

- Update README images
- [INVESTIGATE] Can app size be brought further down?
- [INVESTIGATE] When the user changes an exported file's name, the snackbar still shows the default filename
- [ANSWERED] Can Flet 1.0.3 avoid the focus_chain component (moving between keyboard inputs)?
    * Currently, no. An issue was sent to the Flet team.

- [BUG13] in Appendix A

- [BUG14] in Appendix A
One more question, because of the gain-only rule: what happens to the pending buy fees when an ETF is sold at a loss?
  1. They're included in the loss. The loss grows by the pending buy fees plus the sale fee, and nothing stays pending. This is how costs usually count in a capital loss, so the zainetto ends up with the same total as a sale at a gain, just reported as one bigger loss.
  2. They stay pending until a later sale at a gain. If you sell the whole position at a loss, they're lost for good.
I'd guess 1, but your Fineco statements would show which. 



## AFTER REFACTOR IS COMPLETE:

- Re-record every transaction



## BACKLOG-BIG

- Region allocation
- Sector allocation
- Non-chronological insertions
- Bonds
- Bonds ETFs
- Markdown for TransactionView
- Markdown for AnalysisView
- iOS UI
    - NavigationBar