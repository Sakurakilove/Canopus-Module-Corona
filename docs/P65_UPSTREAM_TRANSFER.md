# RW6 manager 1.3.4-p65: upstream transfer alignment

The manager is merged with AstralSightStudios/Canopus-Module-Corona
`ee58bed` (the full revision is recorded in `upstream-transfer.json`).

The application receiver lifecycle, file adapter, transfer journal, resource
operation queue, activation/storage helpers and receive page are taken directly
from that revision. The receiver retains that implementation with the two
bounded fixes below. The protocol is the
official version 2 H/T/P/F/C/A/E protocol; no additional phone-side message,
alternate resource-pack format or acknowledgement shortcut is introduced.
Acknowledgements still follow completed native file writes. Upstream
background/calendar override support and its page lifecycle fixes are merged
with the dependent storage helpers rather than copying only one receiver file.

RW6 changes retained outside the transport are the exact P65 resource-pack
capability checks, module-status retry on page entry and the rounded-screen
header inset. Calendar/background *format support in the manager* does not
enable those native runtime features on P65: this target accepts the supported
static application/settings/control-center icons only.

## Update

Update `Corona-Manager-RW6-1.3.4-p65.rpk` through AstroBox's QuickApp entry,
close and reopen Corona, then retry the existing `.crpack` through AstroBox's
resource-pack entry. Existing themes and Canopus/Corona native installations
are retained; the two BIN installers remain at version 0.3.6.

## Evidence and limits

The previous 1.3.3-p65 receiver, file adapter, journal and receive page were
already identical to upstream. This update aligns the remaining dependent
manager helpers and pages with the latest upstream and fixes two queue/error
association defects; it is not evidence that the reported `res_pack acknowledgement timed out (T)` is fixed on hardware.
That message identifies a missing T response, not its cause. The receive page
is opened by the official receiver only at P (file preparation), after the T
manifest exchange; remaining on the homepage cannot identify which T request
timed out. `Backtrace capture disabled` is a Rust diagnostic setting, not a
watch-side transfer failure.

No on-device validation is required for release; the user tests installation.

## Code fixes without changing the phone protocol

* `interconnect-send.ts` releases normal P65 response waits on subsequent peer
  traffic or after 1.5 seconds if the native SDK neither succeeds nor fails.
  This is local queue progress, not confirmation that a message was delivered;
  AstroBox still waits for actual protocol replies and retries missing ones.
  Q keeps native delivery confirmation and times out as failure; connection
  shutdown cancels all pending sends. Other targets retain confirmed sends.
* T/P errors use the incoming request's theme ID. Previously a rejected begin
  for a second theme used the unfinished first theme's ID. AstroBox discards
  replies for another theme *before* checking errorCode, so a real rejection
  could appear as a T timeout. The unfinished transfer remains intact.

A focused host regression transfers H/T/P/F/A/C/finish with all native send
callbacks deliberately absent and checks durable bytes before A; Q cannot
terminate on the fallback. Another regression confirms a rejected second
theme is identified correctly without changing the first transfer's journal.
Native send callback absence on the actual watch has not been proven; this
fix removes that indefinite wait regardless. No acknowledgement is sent
before persistence and the file API/journal format are unchanged.
