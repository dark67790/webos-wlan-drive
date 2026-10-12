# External WLAN module build workflow

This is a plan for building a `.ko` as an external module. It does not build or replace the TV kernel image.

## What the LG bundle tells us

The inspected `webOS 6.0 ON 1.0` archive `_2` contains `soc/o20n_mt7921.tgz`. Its README specifies the LG webOS TV SDK / Starfish cross toolchain version `5.0.0-20191125`:

- Host: x86_64 Linux
- Target: AArch64 (`ARCH=arm64`)
- Compiler prefix: `aarch64-starfish-linux-`
- Expected compiler path after SDK installation: `toolchain/sysroots/x86_64-starfishsdk-linux/usr/bin/aarch64-starfish-linux/aarch64-starfish-linux-gcc`
- 64-bit-host installer named in the README: `starfish-sdk-x86_64-aarch64-toolchain-5.0.0-20191125.sh`

The installer is not inside `o20n_mt7921.tgz`; the README says to copy it in separately. This Termux host is AArch64, while LG documents an x86_64-host SDK, so that SDK is not expected to run natively here. The toolchain installer has not been found in the current shared-storage files.

The vendor makefile is `gen4m_mt7921/Makefile_WEBOS60_O20N_64BitMachine`. It points Kbuild at `../linux-rockhopper_build_o20` and runs `make -C $(LINUX_SRC) M=$(DRIVER_DIR) ... modules`. That is the external-module build pattern we should use.

## Compatibility status

The prepared O20N build tree in `_2` records `4.4.84-214` in `include/config/kernel.release` and `include/generated/utsrelease.h`. The TV runs `4.4.84-229.kcl4tv.6`; its installed modules report vermagic `4.4.84 SMP preempt mod_unload aarch64`.

The package README and makefile are specifically for the MT7921 O20N WLAN driver. The TV currently has a loaded module named `wlan_mt7668_usb`, with an installed `wlan_mt7668.ko`. This bundle confirms LG's toolchain and build method, but does not prove that its kernel build tree matches the TV or the WLAN device we intend to support.

## AR9271 findings

The first adapter target is the USB Atheros AR9271. Its Linux driver is `ath9k_htc` (with ath9k common/hardware code, mac80211, cfg80211, and USB dependencies); it is not a standalone source file or firmware-only addition. The LG `_2` bundle is the kernel source/build package we were discussing. It contains a prepared `linux-rockhopper_build_o20` tree and a partial `kernel-source` directory. Its `drivers/net/wireless/ath/ath9k` area has headers, but archive listing shows only `htc.h` and `htc_hst.h` from the HTC driver side—not the `htc_drv*.c` implementation files needed to build `ath9k_htc`. So we can use it as a reference/base tree, but it is not a complete source checkout for this driver. The prepared TV `.config` also has `# CONFIG_ATH_CARDS is not set` and `# CONFIG_MAC80211 is not set`. We can try the approach you meant: build mac80211 plus the AR9271 stack as external modules, leaving the TV kernel image alone. The TV has `CONFIG_CFG80211=y` and `CONFIG_MODULES=y`; the candidate module stack is mac80211, ath9k common/hardware, and ath9k_htc. The LG archive has a prepared base tree, but its source is partial and lacks the HTC implementation files, so we must fill those from a matching source revision and ensure all module dependencies are built against the same prepared tree. The LG prepared tree says `4.4.84-214`, so it is a compile experiment until we find a tree matching the TV's `4.4.84-229.kcl4tv.6` release.

The AR9271 requires firmware too. The driver expects `htc_9271.fw` (newer linux-firmware packaging uses `ath9k_htc/htc_9271-1.4.0.fw`); the firmware is distributed in the separate `linux-firmware` project, not automatically included just because the kernel source is present. The TV must have a supported firmware-loading path and the blob must be installed at the requested path. The LG kernel bundle's archive listing did not show this AR9271 firmware.

## GitHub Actions build plan

Compilation belongs on a GitHub-hosted x86_64 Linux runner (for example, `ubuntu-22.04`), not on this AArch64 Termux device. Termux is used to manage the repository and review the resulting artifact. The runner should build an external `.ko` only; it must never build or flash a TV kernel image.

The workflow is not yet a runnable AR9271 build: the exact SDK installer is not present in the repository or confirmed at a trustworthy download location, and the LG archive's source tree is partial and lacks the AR9271 HTC implementation files. Do not substitute a similarly named Starfish SDK without checking its target triple and version. Keep large LG archives and SDK installers out of Git; fetch them in the workflow from an authorized, pinned source or store them as access-controlled GitHub Actions artifacts/secrets as appropriate.

Once those inputs are confirmed, the workflow should:

1. Run on `ubuntu-22.04` and print/check the runner architecture (`x86_64`).
2. Use the LG `_2` archive's prepared tree as the initial reference, and obtain the missing AR9271 HTC/dependency sources plus a TV-matching kernel build tree before treating an output as loadable. Then fetch the exact `starfish-sdk-x86_64-aarch64-toolchain-5.0.0-20191125.sh` installer; verify published or independently recorded SHA-256 checksums before use. The exact installer source and checksum are still outstanding.
3. Install the SDK into the job workspace and verify the compiler with `aarch64-starfish-linux-gcc -dumpmachine`.
4. Stage the AR9271 driver/dependencies and its `htc_9271.fw` firmware as separately reviewable artifacts. Build mac80211 and the ath9k dependencies as modules, then ath9k_htc, all against the same compatible prepared Kbuild tree. The actual build invocation will need to follow the selected source tree's Kbuild layout:

   ```sh
   make -C "$KDIR" M="$DRIVER_DIR" ARCH=arm64 \
     CROSS_COMPILE="$CROSS_COMPILE" modules
   ```

5. Inspect the `.ko` metadata and required symbols, then upload it as a workflow artifact for review. Do not copy it to or load it on the TV automatically.

Compatibility remains unresolved: the LG O20N bundle's prepared tree reports `4.4.84-214`, while the TV runs `4.4.84-229.kcl4tv.6`; the bundle targets MT7921, while the TV currently loads MT7668 WLAN; the AR9271 HTC files are absent from the inspected source archive and mac80211/ath support is disabled in the TV config. The plan is to build that support as modules, not rebuild the TV kernel. A successful runner build would establish only that the module compiles against that bundle, not that it can load on this TV. No build, install, or module load has been performed.