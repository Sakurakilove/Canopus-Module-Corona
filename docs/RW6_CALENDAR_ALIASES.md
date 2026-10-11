# P65 calendar static image aliases

Profile: xiaomi-p65-3.100.043; AP SHA256
`a19b601477569765103eaf468b937bd8026b4d68ffa5c896bde222a79e475858`.

The original resource inventory covered launcher/calendar and launcher/cal_launcher128,
but omitted the built-in perpetual_calendar application and notification resources:

| Source below /resource/ | Native dimensions |
| --- | --- |
| app/perpetual_calendar/launcher_icon.bin | 96×96 |
| app/perpetual_calendar/launcher.bin | 144×144 |
| app/notifications/calendar_icon.bin | 160×160 |
| app/notifications/calendar.bin | 48×48 |

Firmware application-descriptor code checks
`/data/quickapp/app/perpetual_calendar/calendar_icon.bin` and selects that
installed-file copy when present. The path literal is at RAM 0x3c23e148;
references include flash 0x0c7ebe14, 0x0c7ec87c and 0x0c7efecc.
The stock resource fallback literal is at RAM 0x3c23efcc.
Launcher layouts also select `/resource/app/launcher/cal_launcher128.bin`
for app ID 0x45, already covered by previous packs.

A theme may map the exact installed-copy path to its 96px calendar replacement.
Both manager validation and native capability validation allow only this exact
non-resource alias. Cache retirement includes all five additional sources.
Generic QuickApp hooks and dynamic calendar generation remain disabled.
This extends firmware-backed path coverage; actual calendar appearance still
requires the user's watch test.

The native module changes, so updating only the RPK/CRPack is insufficient.
Existing installs use Canopus Remove → reboot → Start → new signed module
installer → Enable → Activate. Removing the Canopus module does not delete
Corona's QuickApp theme directory. Supervisor duplicate protection is retained.
