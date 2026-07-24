# Gmail integration and known limitations

The integration observes Gmail’s rendered DOM because no Gmail API/OAuth flow is part of this thesis phase. Gmail does not publish a stable DOM contract, class names may change, conversations can virtualize messages, and message identifiers may sometimes be absent. The adapter returns an explicit unavailable state instead of inventing metadata.

The adapter checks only known open-message containers and never iterates inbox rows. Automatic mode observes only the main Gmail area, waits 600 ms after DOM changes, and processes a newly selected message ID once. It disconnects on `pagehide`.

## Manual Gmail demonstration

1. Start FastAPI and the dashboard, then build and load the unpacked extension.
2. Reload Gmail after installing or rebuilding so the content script is injected.
3. Open one email conversation and select the desired message.
4. Open Sentinel, choose **Current Gmail message**, leave automatic tracking off, and click **Analyze Current Email**.
5. Inspect sender, domain, open count, prototype score, indicators, recommendation, and source.
6. Click **View in Dashboard**, then refresh the dashboard.
7. For opt-in automatic behavior, enable **Automatic tracking** and select a different Gmail message. Disable it again when finished.

If Sentinel reports “analysis unavailable,” reopen the message and retry. Persistent failure likely means Gmail changed one of the isolated selectors; update the adapter fixture/tests before changing other extension modules.
