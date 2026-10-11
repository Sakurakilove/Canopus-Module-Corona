# RW6: AstroBox component installation

Use the P65 adaptation only with Redmi Watch 6 firmware **3.100.043**. The
component workflow follows the official Canopus/Corona architecture. The RW6
builds have not been listed in the official AstroBox catalog yet. Install the
adapted files locally; the current upstream catalog builds target other devices.

| Artifact | AstroBox installation type | Role |
| --- | --- | --- |
| `01-Canopus-RW6-Start.bin` | Watchface / Lua watchface | Native Canopus framework bootstrap and manager |
| `02-Corona-RW6-Install.bin` | Watchface / Lua watchface | Signed native Corona module installer |
| `Corona-Manager-RW6.rpk` | **QuickApp / Application** | Theme manager |
| Separate `.crpack` files | **Resource pack** | Theme import |
| `Corona-Editor-RW6.abp` | AstroBox plugin (optional) | Theme authoring |

Install and open the Canopus bootstrap, then install and open the Corona module
installer. In the native Canopus Manager, enable `corona` and immediately
activate it. Install the RPK as a **QuickApp**, then import themes using AstroBox's
resource-pack flow and choose the theme in Corona Manager. Themes are not
embedded in the RPK. No firmware flashing is involved.

After reboot, manually open the Canopus bootstrap to restore enabled modules
and the saved theme. You can subsequently switch to any other watchface.

## `invalid watchface id` when installing the RPK

This error originates in AstroBox's watchface installation path, not the Corona
QuickApp. If the install preview says Watchface, cancel it and choose the
QuickApp/Application installation entry. Do not rename the RPK to `.bin` or
repack the signed ZIP.

The delivered RPK contains both QuickApp manifests, the RPK signature block,
and a ZIP comment with the `toolkit` marker. The published legacy AstroBox
classifier checks the last 256 bytes for that marker; the NG classifier also
recognizes `manifest-watch.json`. Both rules identify this artifact as a
QuickApp. If the correct entry still selects Watchface, record the AstroBox
version and installation entry to investigate the client behavior. Hardware
installation and client UI behavior are not established by these file checks.

Public manager download:
https://github.com/Sakurakilove/Canopus-Module-Corona/releases/tag/rw6-v0.3.1

## Installer result 6 / error -105

`CANOPUS_SUP_ERR_STAGE_DUPLICATE` means Supervisor already holds a record for
`corona`. It is not a signature error and does not show that Corona is active.
The 0.3.1 installer explains this result instead of displaying installation
failure. It does not bypass duplicate protection or change the existing slot.
Inspect the record in the native Canopus Manager, enable the module and choose
**Immediately activate**. Corona QuickApp cannot detect a disabled native module.
The installer keeps other errors, including signature failures, as failures.

Original theme material remains in the user's private repository. No upstream
PR or official catalog publication is included in this delivery.
