# RW6 P65 manual icon component, beta 4

Target: Redmi Watch 6 standard/P65, AP 3.100.043, AP SHA256
`a19b601477569765103eaf468b937bd8026b4d68ffa5c896bde222a79e475858`.

The user supplied two device screenshots of the separate v2 diagnostic:
`FW 3.100.043 / build.prop OK`, followed by
`PASS: load / identity / driver / exit`, with Fold icons decoded correctly.
This confirms the isolated probe's loader lifecycle and exact driver checks.
It does not validate this new component's registration, cache mutation or system replacement.

Beta1 and Beta2 both failed on the device with shell wait status 65280
(exit 255). Beta2's native marker remained at stage 0. That does not establish
whether the initializer ran. Global system icon replacement remains unverified.

Beta3 fixes a reproduced native control-driver lifetime bug. P65 open invokes
fops->open with a temporary struct file on the stack, then files_allocate copies
flags, position, inode and f_priv into a different descriptor-table struct file.
Beta2 keyed clients by the temporary pointer, so subsequent read/close returned
EBADF. Beta3 stores a bounded client pointer in f_priv at offset 20. Actual
firmware open/files_allocate execution gives Beta2 read=-1/close=-9 and Beta3
read=48/close=0, with the same modeled inode resolution and descriptor table.
The report is analysis/p65-file-context-regression-beta3.json. This defect would
break the control receipt, but does not by itself explain shell exit 255.

P65 f_priv evidence: image-storage open at 0x0c247ea8 loads the field at
stack file+20 and passes it to files_allocate at 0x0c2440c4. The latter writes
it to descriptor+20 at 0x0c24426c. The live open veneer 0x0c8bef00 targets
0x1c1580e5, matching that body in the startup-copy image beginning 0x0c0efdc4.
The tests execute the runtime alias, native allocation copy and read dispatch;
path/inode resolution, task lookup and descriptor-table storage are modeled.

Native I/O now uses the same live AP veneers as stock modlib/LVGL:
open 0x0c8bef01, close 0x0c8bdba9, read 0x0c8beaf1, write 0x0c8be041.
These branch to runtime aliases 0x1c1580e5, 0x1c154d9d, 0x1c158721,
0x1c159a2d. Direct calls to image-storage bodies at 0x0c24xxxx are removed
from the binding. The backing bodies are present in the supplied AP copy image;
previous documentation describing all these bodies as absent ROM was incomplete.
Runtime patch/cache behavior and actual hardware access still need device testing.

Beta3 also failed on the device with exit 255/raw 65280 and stage 0.
The previous statement that stdout redirection captures insmod errno was wrong.
Exact AP NSH command code at 0x0c5b15e4 sends insmod errors through console
vtable+0x14 to the stderr descriptor (+0x4ac). Its redirect routine at
0x0c5ae410 changes only stdout (+0x4a8); the parser recognizes > and >>,
not POSIX 2>&1. Beta4 removes the misleading error-log capture entirely.
The device failure's direct cause remains unknown.

Beta4 validates each immutable mapping directly without allocating a 512-byte
legacy rule or entering the 512-byte sorting workspace. It also checks that
the compact resolver destination and the CRC-validated file are identical.
The standalone build omits config.c, garbage-collects unreachable functions,
and merges per-function ARM unwind sections in p65_standalone_sections.ld.
The final component is 24,692 bytes, 14 sections, 283 relocations, zero imports
and zero constructors. Native file CRC uses two nibble lookups per byte instead
of eight polynomial iterations, preserving the same CRC32 values. LVGL slot 5
is correctly named read, slot 6 write; their comparison values are unchanged.

The Lua controller checks residency before writing assets. Active compatible
components are reused without rewriting live files; foreign endpoints stop
installation. For a new load it copies and verifies only the module, releases
payload/readback memory, performs a collection, and loads the control component
before staging any of the 102 icon assets. A failed staging operation retains
the stock-mode component and can be retried without a second insmod. Package
assembly verifies asset CRC32 as well as byte length against generated constants.

This component uses the stock loader and an exact-version standalone module,
not the withdrawn Supervisor. `CANOPUS_P65_DEPLOYMENT_ENABLED` remains zero;
the full Corona P65 target remains gated. No application registration, registry,
autoload, boot setting, firmware flashing or existing manager configuration is modified.

## Operation and lifetime

Opening the Lua controller displays 128px previews and reads existing status.
INSTALL validates the screen and build.prop, checks residency, verifies/copies
rw6-component-v4.bin, manually loads rw6_corona_v1, then stages 102 native assets
into `/data/quickapp/files/ng.lst.corona/themes/rw6-{orbit,fold}-v1/`.
Resources preserve their native 80/96/128/144/160 dimensions and each file is
read back byte for byte. Compatible active components are not staged again.
Shell success is insufficient: `/dev/rw6-corona-v1` must return the exact 48-byte
status schema and successful registration result.

The module initializer checks exact embedded firmware strings and eight native
driver fields; it rejects an existing endpoint. It installs only a control driver,
without changing the LVGL filesystem callback. The register_driver AP veneer and runtime body recovered from the copy image
are executed in the full-loader tests. The body preserves inode_reserve errors
and writes fops/private fields; inode allocation and locking are modeled.
Registration on the actual watch remains a device-test boundary.

ORBIT/FOLD send a 16-byte frame via Lua file I/O. The control driver's close
callback validates all 51 selected assets' exact size and CRC32 through native
file calls, then atomically installs its own LVGL open callback and selects an
immutable indexed snapshot. Changes and native path cache drops execute on the Lua
client's close caller, rather than on the shell installer task. STOCK selects
pass-through and clears the same 51 source keys. No guessed UI repaint function
or UI object traversal is used: leave the controller and reopen the system app
list to let stock objects rebind their image sources.

The callback and control endpoint remain resident even in STOCK mode. After any
driver registration attempt, the unload callback returns `-16`; this intentionally
prevents freeing firmware-reachable callback code, including after an uncertain
registration error. Do not run rmmod, delete/replace modules live, or automate
load retries. A normal power cycle does not autoload this component; cold boot
stability has not been established by this delivery.

Mapped read failures fall back to stock files. Source writes are not redirected.
Missing, corrupt, truncated or extended selected assets fail before selection or
callback installation. Stock restoration needs no theme asset files. An unrelated
driver callback is never overwritten. Four bounded independent file contexts
handle fragmented writes and status cursors; only close commits a complete frame.

## Wire format (little endian)

Control: four u32 words: `0x43365452`, nonzero request sequence, mode (0 stock,
1 orbit, 2 fold), reserved zero. Overlong/short/invalid frames fail.

Status: twelve words: `0x48543652`, schema 1, mode, callback-installed flag,
redirect count, fallback count, request sequence, signed result, cache epoch,
signed registration result, rule count 51, module schema `0x00030004`.
The controller confirms its exact sequence, success result and selected mode.
It reads the receipt even when close fails to preserve the actual error code.

## Offline build and tests

At the extracted delivery root set `RW6_PROJECT_ROOT` to that root,
`CANOPUS_P65_FIRMWARE` to the extracted AP, and CLANG/LD_LLD to ARM-capable
Clang/lld. Canopus must be a sibling of Canopus-Module-Corona under upstream/
or source/. The stock framework must not be built or installed as a dependency.

```sh
cd source/Canopus-Module-Corona
scripts/build-p65-standalone.sh
python3 tests/test_p65_standalone.py -v
python3 tests/test_p65_full_loader.py -v
python3 tests/test_p65_controller.py -v
cd ../..
python3 build_rw6_theme_watchface.py
python3 tests/test_rw6_system_watchface.py -v
```

Dependencies: Pillow, lupa Lua 5.4, Unicorn, pyelftools, Canopus CLI (Rust).
The script generates fixed rules, sizes and CRCs from the two CRPacks. It builds
an ET_REL with Thumb entry 1, zero imports, no constructors, and verifies it with
a component-specific exact-AP SDK overlay. The base SDK and deployment gate are
unchanged. Desktop cover generation falls back to English when Noto CJK is absent.

18 native component tests cover all 102 mapped paths, live read/write dispatch,
control context migration, fragmented commands, checksums, cache dispatch and
failure retention. Seven full-loader tests execute stock insmod, ELF parsing,
section layout, all 283 relocations, real symbol resolution, entry and registry;
they also exercise copied-file ownership and register_driver's runtime body.
Allocator, underlying file bytes, stat, locks, inode resolution, task lookup and
cache retirement are modeled. These checks do not establish real filesystem,
cache or cold-boot behavior.

14 Lua tests (including actual 32-bit Lua 5.4) and seven container tests cover
manual operation, full readback, shell-exit/stage distinction, exact matching receipts,
all 184 embedded files, 102 native assets, 80 previews and corruption rejection.
The current component/controller/container group has 46 passing tests. Shared
I/O binding regressions are checked separately after the veneer correction.

Full Corona Manager support, immediate UI refresh, cold boot behavior and real
system menu replacement remain unverified. Treat this as a manually controlled
system icon beta, not three officially supported components.

The controller also avoids unsigned-number comparisons and floating division
for CRC/framing. Its CRC is compared as four wire bytes, status words decode
within signed 32-bit bounds, and sequence wraps within the signed range. The
Lua suite includes actual Lua 5.4 compiled with LUA_32BITS=1 (32-bit integers
and floats), exercising installation, partial writes, three themes, stage
errors, checksums and wrap. Set RW6_LUA32_BINARY to that interpreter to repeat
this optional regression; ordinary tests use Lupa Lua 5.4. No firmware bypass
is used.
