# RW6 manager 1.3.5-p65: upstream transfer alignment and recovery

The manager is merged with AstralSightStudios/Canopus-Module-Corona
`ee58bed` (the full revision is recorded in `upstream-transfer.json`).

The application receiver lifecycle, file adapter, transfer journal, resource
operation queue, activation/storage helpers and receive page are taken directly
from that revision. The receiver retains that implementation with the
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

Update `Corona-Manager-RW6-1.3.5-p65.rpk` through AstroBox's QuickApp entry,
close and reopen Corona, then retry the existing `.crpack` through AstroBox's
resource-pack entry. Existing themes and Canopus/Corona native installations
are retained; the two BIN installers remain at version 0.3.6.

## Evidence and limits

The previous 1.3.3-p65 receiver, file adapter, journal and receive page were
already identical to upstream. This update aligns the remaining dependent
manager helpers and pages with the latest upstream and fixes two queue/error
association defects; it is not evidence that the reported `res_pack acknowledgement timed out (T)` is fixed on hardware.
That message identifies a missing T response, not its cause. The receive page
was opened by the official receiver only at P (file preparation), after the T
manifest exchange. Version 1.3.5 opens the same page from T begin so the
manifest stage and its actual rejection message are visible. `Backtrace capture disabled` is a Rust diagnostic setting, not a
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

## 1.3.5: partial manifests and new tasks

AstroBox publishes a resume token after T begin, before transmitting the file
manifest. The receiver formerly required `manifestComplete` for resume, so a
valid retry of an interrupted manifest was rejected. Resume now verifies the
matching theme/count/total, replays and validates the known file prefix, and
appends only the missing tail. Existing file bytes, chunk geometry and bitmap
remain unchanged. A mismatch still rejects without modifying saved state.

A new AstroBox task explicitly sends `mode=replace`. It can now supersede the
single unfinished transfer record even when the previous task targeted a
different theme. Only the requested theme directory is replaced; other theme
directories and installed packages are retained. This cancels the previous
task's *resume record*: to send that abandoned theme later, create a fresh
task. No active-theme protection is removed.

The official receive page opens at begin instead of waiting for P; it uses the
existing style and now displays the full receiver error text. There is no new
protocol or phone-side requirement. The supplied packs each have 109 files
(including one manifest), well within receiver count/size/path limits.

Focused regressions cover manifests interrupted after 0/1/all entries, reboot
while replaying the prefix, mismatched replay entries, and a new replace task
after an unfinished different theme. Type checking and RPK build pass. The
user confirmed they created a new task, so the partial-resume fix alone is not
claimed as the cause of their error. The exact on-watch rejection remains
unconfirmed until the user tries this release and views its detailed message.
