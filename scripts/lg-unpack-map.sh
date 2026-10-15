#!/usr/bin/env bash
# Recursively unpack tar-in-tar-in-zip packages and print a map of what is inside.
# Usage: lg-unpack-map.sh <archive> [dest-dir]     (default dest: ./lg-unpacked)
# Output: dest/ (extracted), dest.map.txt (the map), dest/.kernel_roots (kernel source dirs found)
set -uo pipefail

src="${1:?usage: $0 <archive> [dest]}"
dest="${2:-./lg-unpacked}"
mkdir -p "$dest"
dest="$(cd "$dest" && pwd)"
skip="$(mktemp)"
map="${dest}.map.txt"

extract() {  # extract <file> <dir>  -> 0 if it was an archive
  local f="$1" d="$2" mt
  mt="$(file -b --mime-type "$f")"
  case "$mt" in
    application/zip) unzip -q -o "$f" -d "$d" ;;
    application/x-tar|application/gzip|application/x-gzip|application/x-xz|application/x-bzip2|application/zstd)
      tar -xf "$f" -C "$d" --no-same-owner 2>/dev/null ;;
    *) return 1 ;;
  esac
}

echo ">> extracting $src"
extract "$src" "$dest" || { echo "not a recognised archive: $src"; exit 1; }
chmod -R u+rwX "$dest"

for pass in $(seq 1 12); do
  found=0
  while IFS= read -r -d '' f; do
    grep -qxF "$f" "$skip" && continue
    if extract "$f" "$(dirname "$f")"; then
      echo ">> pass $pass: unpacked ${f#$dest/}"
      rm -f "$f"; found=1
    else
      echo "$f" >> "$skip"
    fi
  done < <(find "$dest" -type f -size +100k -print0)
  chmod -R u+rwX "$dest"
  [ "$found" -eq 1 ] || break
done

{
  echo "=============== MAP of $src ==============="
  echo; echo "== size"; du -sh "$dest"
  echo; echo "== top-level layout (depth 3)"
  find "$dest" -mindepth 1 -maxdepth 3 -type d | sed "s|$dest/||" | sort | head -80

  echo; echo "== kernel source roots (Kconfig + Makefile + arch/)"
  : > "$dest/.kernel_roots"
  while IFS= read -r k; do
    d="$(dirname "$k")"
    [ -f "$d/Makefile" ] && [ -d "$d/arch" ] || continue
    echo "$d" >> "$dest/.kernel_roots"
    v=$(awk -F' *= *' '/^(VERSION|PATCHLEVEL|SUBLEVEL|EXTRAVERSION)/{a[$1]=$2} END{printf "%s.%s.%s%s",a["VERSION"],a["PATCHLEVEL"],a["SUBLEVEL"],a["EXTRAVERSION"]}' "$d/Makefile")
    echo "  ${d#$dest/}   (version $v)"
  done < <(find "$dest" -maxdepth 8 -type f -name Kconfig -path '*/Kconfig' -not -path '*/arch/*' -not -path '*/drivers/*')

  echo; echo "== arm64 / LG defconfigs"
  find "$dest" -path '*arch/arm64/configs/*' -type f | sed "s|$dest/||" | head -60
  find "$dest" -type f \( -iname '*lg*defconfig*' -o -iname '*webos*defconfig*' -o -iname '*.config' \) \
    -not -path '*/arch/arm64/configs/*' | sed "s|$dest/||" | head -30

  echo; echo "== prebuilt kernel output (Module.symvers / vmlinux / Image / kernel.release)"
  find "$dest" -type f \( -name Module.symvers -o -name vmlinux -o -name System.map -o -name Image \
       -o -name 'Image.gz*' -o -name kernel.release -o -name '*.ko' \) -printf '%P (%s bytes)\n' | head -60

  echo; echo "== toolchains (cross gcc binaries)"
  find "$dest" \( -type f -o -type l \) -name '*-gcc' | sed "s|$dest/||" | head

  echo; echo "== out-of-tree drivers (obj-m outside kernel's own drivers/net/fs/...)"
  grep -rl --include=Makefile --include=Kbuild --include='*.mk' 'obj-m' "$dest" 2>/dev/null \
    | grep -vE '/(arch|drivers|net|fs|sound|crypto|lib|kernel|mm|security|block|samples|tools|Documentation|scripts)/' \
    | xargs -r -n1 dirname | sort -u | sed "s|$dest/||" | head -40

  echo; echo "== driver-looking dirs (wifi / bt / wlan / usb vendors)"
  find "$dest" -maxdepth 8 -type d \( -iname '*wlan*' -o -iname '*wifi*' -o -iname '*mt79*' -o -iname '*rtl*' \
       -o -iname '*qca*' -o -iname '*bcm*' -o -iname '*realtek*' -o -iname '*mediatek*' \) \
       -not -path '*/Documentation/*' | sed "s|$dest/||" | sort | head -40

  echo; echo "== other archives left (not unpackable / not tar)"
  sed "s|$dest/||" "$skip" | head -20

  echo; echo "== biggest 25 files"
  find "$dest" -type f -printf '%s %P\n' | sort -rn | head -25
} 2>&1 | tee "$map"
rm -f "$skip"
echo; echo "map saved to $map"
