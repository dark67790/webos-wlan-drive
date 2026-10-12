# webos-wlan-drive

Project workspace for webOS WLAN drive tooling.

## Status

Kernel details are recorded locally. The GitHub Actions build plan, AR9271 source/firmware findings, and compatibility limits are in [BUILD_WORKFLOW.md](BUILD_WORKFLOW.md).

## TV kernel reference files

Collected from an LG webOS 6.4 TV (`LG1212`, AArch64):

- `tv-kernel-info.txt` — kernel release, device tree identity, module inventory, and environment details.
- `tv-kernel.config` / `tv-kernel.config.gz` — kernel config from `/proc/config.gz`.
- `tv-module-metadata.txt` — WLAN/Bluetooth module metadata, vermagic, and relevant config flags.

The running kernel reports `4.4.84-229.kcl4tv.6` and modules report vermagic `4.4.84 SMP preempt mod_unload aarch64`. The TV did not expose a matching kernel build tree or headers, so these files are reference information and do not by themselves make the external module buildable.
