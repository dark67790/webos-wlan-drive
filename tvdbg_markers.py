#!/usr/bin/env python3
"""Insert TVDBG printk markers into the ath9k_htc init path (Linux 4.4.84).

usage: python3 tvdbg_markers.py <kernel source root>

Every marker is  printk(KERN_EMERG "TVDBG ...")  so it lands in the kernel log
ring (and on the UART console when the console loglevel is raised) no matter
what the log level settings are.  The last TVDBG line seen before the TV dies
tells us which step it was in.

"Slow" markers (process context only) also msleep() so the log writer on the
TV can flush the line to disk before the next step runs.  A crash can then only
lose the step it is in, not the ones before it.  Set SLEEP_MS below if needed.

Every anchor must match exactly once; the script stops with an error otherwise,
so a silent half-patch can never be built.
"""
import re
import sys
from pathlib import Path

root = Path(sys.argv[1]) / "drivers/net/wireless/ath/ath9k"
if not root.is_dir():
    sys.exit(f"not found: {root}")

SLEEP_MS = 600
P = 'printk(KERN_EMERG "TVDBG %s\\n");'
# counted marker for callbacks that fire many times: only the first N print
def counted(fmt, args=""):
    a = (", " + args) if args else ""
    return ('{ static int tvdbg_n; if (tvdbg_n++ < 40) '
            f'printk(KERN_EMERG "TVDBG {fmt}\\n"{a}); }}')


def mark(text):
    return P % text


def slow(text):
    return P % text + f" msleep({SLEEP_MS});"


def edit(name, pairs):
    path = root / name
    src = path.read_text()
    for kind, anchor, payload in pairs:
        if kind == "before":
            pat, rep = re.escape(anchor), "\t" + payload + "\n" + anchor
        elif kind == "after":
            pat, rep = re.escape(anchor), anchor + "\n\t" + payload
        elif kind == "after_re":      # insert after the end of a regex match
            pat, rep = anchor, None
        else:
            raise SystemExit("bad kind")
        found = len(re.findall(pat, src, flags=re.S))
        if found != 1:
            sys.exit(f"{name}: anchor matched {found} times (need 1): {anchor[:70]!r}")
        if kind == "after_re":
            src = re.sub(pat, lambda m: m.group(0) + "\t" + payload + "\n", src, count=1, flags=re.S)
        else:
            src = re.sub(pat, lambda m: rep, src, count=1, flags=re.S)
    if "linux/delay.h" not in src:
        src = src.replace("#include", "#include <linux/delay.h>\n#include", 1)
    path.write_text(src)
    print(f"patched {name}: {len(pairs)} markers")


edit("hif_usb.c", [
    ("before", "\tret = ath9k_hif_usb_dev_init(hif_dev);\n\tif (ret)\n\t\tgoto err_dev_init;",
     slow("fw_cb: before dev_init")),
    ("before", "\tret = ath9k_htc_hw_init(hif_dev->htc_handle,",
     slow("fw_cb: dev_init ok, before htc_hw_init")),
    ("before", "\trelease_firmware(fw);\n\thif_dev->flags |= HIF_USB_READY;",
     slow("fw_cb: htc_hw_init returned ok")),
    ("before", "\t/* Alloc URBs */\n\tret = ath9k_hif_usb_alloc_urbs(hif_dev);",
     slow("dev_init: firmware downloaded, before alloc_urbs")),
    ("before", "\t/* RX */\n\tif (ath9k_hif_usb_alloc_rx_urbs(hif_dev) < 0)",
     slow("alloc_urbs: tx ok, before rx urbs")),
    ("before", "\t/* Register Read */\n\tif (ath9k_hif_usb_alloc_reg_in_urbs(hif_dev) < 0)",
     slow("alloc_urbs: rx ok, before reg_in urbs")),
    ("before", "\treturn 0;\nerr_reg:",
     slow("alloc_urbs: all urbs ok")),
    ("after_re",
     r"static void ath9k_hif_usb_reg_in_cb\(struct urb \*urb\)\n\{.*?\tint ret;\n\n",
     counted("reg_in_cb status=%d len=%d", "urb->status, urb->actual_length")),
    ("after_re",
     r"static void ath9k_hif_usb_rx_cb\(struct urb \*urb\)\n\{.*?\tint ret;\n\n",
     counted("rx_cb status=%d len=%d", "urb->status, urb->actual_length")),
])

edit("htc_hst.c", [
    ("before", "\tret = htc_config_pipe_credits(target);",
     slow("htc_init: before config_pipe_credits")),
    ("before", "\treturn htc_setup_complete(target);",
     slow("htc_init: before setup_complete")),
    ("after_re",
     r"\tunsigned long time_left;\n\n(?=\t/\* Find an available endpoint \*/)",
     'printk(KERN_EMERG "TVDBG connect_service enter id=0x%x\\n", service_connreq->service_id); msleep(' + str(SLEEP_MS) + ');'),
    ("before", "\tret = htc_issue_send(target, skb, skb->len, 0, ENDPOINT0);\n\tif (ret)\n\t\tgoto err;\n\n\ttime_left = wait_for_completion_timeout(&target->cmd_wait, HZ);\n\tif (!time_left) {\n\t\tdev_err(target->dev, \"Service connection timeout",
     slow("connect_service: before htc_issue_send")),
    ("before", "\ttime_left = wait_for_completion_timeout(&target->cmd_wait, HZ);\n\tif (!time_left) {\n\t\tdev_err(target->dev, \"Service connection timeout",
     slow("connect_service: request sent, before wait")),
    ("before", "\t*conn_rsp_epid = target->conn_rsp_epid;\n\treturn 0;",
     slow("connect_service: response received")),
    ("before", "\thtc_hdr = (struct htc_frame_hdr *) skb->data;\n\tepid = htc_hdr->endpoint_id;",
     counted("htc_rx_msg len=%u pipe=%u", "(unsigned)len, (unsigned)pipe_id")),
])

edit("htc_drv_init.c", [
    ("before", "\tret = ath9k_htc_wait_for_target(priv);\n\tif (ret)\n\t\tgoto err_free;\n\n\tpriv->wmi",
     slow("probe: alloc_hw ok, before wait_for_target")),
    ("before", "\tpriv->wmi = ath9k_init_wmi(priv);",
     slow("probe: target ready, before init_wmi")),
    ("before", "\tret = ath9k_init_htc_services(priv, devid, drv_info);\n\tif (ret)\n\t\tgoto err_init;\n\n\tret = ath9k_init_device",
     slow("probe: wmi ok, before init_htc_services")),
    ("before", "\tret = ath9k_init_device(priv, devid, product, drv_info);",
     slow("probe: htc services ok, before init_device")),
    ("before", "\tret = htc_init(priv->htc);",
     slow("svc: all services connected, before htc_init")),
    ("before", "\t/* Bring up device */\n\terror = ath9k_init_priv(priv, devid, product, drv_info);",
     slow("init_device: before init_priv")),
    ("before", "\tah = priv->ah;\n\tcommon = ath9k_hw_common(ah);\n\tath9k_set_hw_capab(priv, hw);",
     slow("init_device: init_priv ok")),
    ("before", "\t/* Register with mac80211 */\n\terror = ieee80211_register_hw(hw);",
     slow("init_device: before ieee80211_register_hw")),
    ("before", "\t/* Handle world regulatory */",
     slow("init_device: ieee80211_register_hw ok")),
    ("before", "\tret = ath9k_hw_init(ah);\n\tif (ret) {\n\t\tath_err(common,\n\t\t\t\"Unable to initialize hardware;",
     slow("init_priv: before ath9k_hw_init")),
    ("before", "\tret = ath9k_init_queues(priv);",
     slow("init_priv: ath9k_hw_init ok, before init_queues")),
])

edit("hw.c", [
    ("before", "\tath9k_hw_read_revisions(ah);\n\n\tswitch (ah->hw_version.macVersion) {\n\tcase AR_SREV_VERSION_5416_PCI:",
     slow("hw: __ath9k_hw_init entered, before read_revisions")),
    ("before", "\t/*\n\t * Read back AR_WA into a permanent copy",
     slow("hw: read_revisions ok")),
    ("before", "\tif (!ath9k_hw_set_reset_reg(ah, ATH9K_RESET_POWER_ON)) {\n\t\tath_err(common, \"Couldn't reset chip",
     slow("hw: before set_reset_reg POWER_ON")),
    ("before", "\tath9k_hw_init_defaults(ah);\n\tath9k_hw_init_config(ah);",
     slow("hw: chip reset ok, before init_defaults")),
    ("before", "\tr = ath9k_hw_attach_ops(ah);",
     slow("hw: before attach_ops")),
    ("before", "\tif (!ath9k_hw_setpower(ah, ATH9K_PM_AWAKE)) {\n\t\tath_err(common, \"Couldn't wakeup chip",
     slow("hw: before setpower AWAKE")),
    ("before", "\tah->hw_version.phyRev = REG_READ(ah, AR_PHY_CHIP_ID);",
     slow("hw: awake ok, before phyRev read")),
    ("before", "\tr = ath9k_hw_post_init(ah);",
     slow("hw: before post_init (eeprom)")),
    ("before", "\tath9k_hw_init_mode_gain_regs(ah);\n\tr = ath9k_hw_fill_cap_info(ah);",
     slow("hw: post_init ok, before fill_cap_info")),
    ("before", "\tr = ath9k_hw_init_macaddr(ah);",
     slow("hw: cap_info ok, before init_macaddr")),
    ("before", "\tath9k_hw_init_hang_checks(ah);",
     slow("hw: macaddr ok")),
])
print("done")
