# Redmi Watch 6 / P65 3.100.043

The RW6 profile builds a stock ET_REL Corona module with a native Canopus
descriptor and the existing QuickApp management protocol. It supports static
icons under `/resource/app/`, including calendar launcher aliases, settings and
control-center button states. No theme artwork is included in this repository.
Install separate `.crpack` files using AstroBox's resource-pack flow.

The authoritative AP SHA-256 is
`a19b601477569765103eaf468b937bd8026b4d68ffa5c896bde222a79e475858`.

```sh
export CANOPUS_ROOT=/path/to/Canopus
export CANOPUS_P65_FIRMWARE=/path/to/vela_ap.bin
export CLANG=clang LD_LLD=ld.lld
sh scripts/build-p65-manager.sh
cd manager && npm install && cd ..
python3 scripts/build-p65-manager-app.py
```

Use the matching Canopus recovered-runtime adaptation. Module output is
`build/p65-manager/corona-p65.elf`; the last command writes an RW6-profile RPK
under `build/p65-manager/app`. It temporarily selects the profile and restores
the generic source configuration even if the build fails. Builds need Python
pyelftools; exact-firmware tests additionally require Unicorn 2.1.4.

The adapter recovers P65's 52-byte LVGL filesystem driver with cache size zero,
open callback `0x0c7357d5`, read callback `0x0c735739`, and write callback
`0x0c7356e9`. It uses the actual P65 cache-drop wrapper and owner-task timers,
rather than copying Band cache layouts. Cache invalidation sources are in
`resources/p65-icon-sources.json` and have no dependency on private artwork.

Theme changes retire cached images; reopen the affected system page to update
its existing UI objects. Fonts, generated calendar text, custom backgrounds and
third-party QuickApp icon refresh are currently unsupported in this profile.
The RW6 manager rejects those declarations instead of presenting them as
working features. Its static calendar glyphs are ordinary icon mappings.

After reboot, manually open the Canopus bootstrap to restore enabled modules
and the existing selected-theme configuration. No system autostart is included.
This is a device-test candidate: the earlier standalone application-icon beta
received user confirmation, while the new complete manager chain and expanded
settings/control-center coverage have not been verified on hardware.

Standalone/probe files remain separate diagnostic code. They cannot run
alongside the full Corona hook in the same boot. Restart before switching from
an older standalone beta to the full manager chain.
