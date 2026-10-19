#!/usr/bin/env python3
"""Join local PCSX2 DDS replacement keys to indexed original PNGs or PCSX2 dumps.

Inputs stay read-only; the generated JSON belongs in this checkout's ignored build/.
See docs/TEXTURE-MATCHING.md. Optional dependencies: requirements-textures.txt.
"""
import argparse
from array import array
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
import json
import math
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parent.parent
MAX_PIXELS = 16 * 1024 * 1024
NAME = re.compile(
    r"(?P<texture>[0-9a-f]{1,16})-(?:(?P<palette>[0-9a-f]{1,16})-)?"
    r"(?:(?P<region>r(?:[1-9][0-9]*x[1-9][0-9]*|[0-9a-f]{1,16}))-)?"
    r"(?P<bits>[0-9a-f]{8})(?:-mip(?P<mip>[1-9][0-9]*))?", re.I)


@dataclass(frozen=True)
class TextureKey:
    texture: int
    palette: int | None
    bits: int
    region: str = ""
    mip: int = 0

    def fields(self) -> dict:
        return {"texture_hash": f"{self.texture:016x}",
                "palette_hash": f"{self.palette:016x}" if self.palette is not None else None,
                "bits": f"{self.bits:08x}", "region": self.region, "mip": self.mip}

    def dump_dimensions(self) -> tuple[int, int] | None:
        if self.region:
            region = re.fullmatch(r"r([0-9]+)x([0-9]+)", self.region)
            if not region:
                return None  # Legacy packed-region keys remain filename-only evidence.
            width, height = map(int, region.groups())
        else:
            width, height = 1 << ((self.bits >> 6) & 15), 1 << ((self.bits >> 10) & 15)
        return max(1, width >> self.mip), max(1, height >> self.mip)


def parse_key(stem: str) -> TextureKey:
    """PCSX2 filename key; retain region and mip, clear only the retired TCC bit."""
    m = NAME.fullmatch(stem)
    if not m:
        raise ValueError("not a supported PCSX2 texture filename")
    return TextureKey(int(m["texture"], 16), int(m["palette"], 16) if m["palette"] else None,
                      int(m["bits"], 16) & ~0x4000, (m["region"] or "").lower(),
                      int(m["mip"] or 0))


def dds_dimensions(path: Path) -> tuple[int, int]:
    """Read the DDS header only, without decoding or authenticating its image payload."""
    with path.open("rb") as f:
        head = f.read(148)
    if len(head) < 128 or head[:4] != b"DDS " or struct.unpack_from("<I", head, 4)[0] != 124:
        raise ValueError("invalid or truncated DDS header")
    if struct.unpack_from("<I", head, 76)[0] != 32:
        raise ValueError("invalid DDS pixel-format header")
    if head[84:88] == b"DX10" and len(head) < 148:
        raise ValueError("truncated DDS DX10 header")
    height, width = struct.unpack_from("<II", head, 12)
    if not width or not height or width * height > MAX_PIXELS:
        raise ValueError("unsupported DDS dimensions")
    return width, height


def _column8(x: int, y: int) -> int:
    # PSMT8 byte addressing, expressed from PCSX2's columnTable8 (GPL-3.0+).
    # See CREDITS.md for the exact reference revision.
    value = ((x & 1) << 2 | (x & 6) << 3 | (x & 8) >> 2 |
             (y & 1) << 3 | (y & 2) >> 1 | (y & 12) << 4)
    return value ^ ((((y >> 1) ^ (y >> 2)) & 1) << 5)


@lru_cache(maxsize=16)
def _block_order(width: int, height: int) -> array:
    tile = sorted(range(256), key=lambda i: _column8(i % 16, i // 16))
    return array("I", ((by + i // 16) * width + bx + i % 16
                       for by in range(0, height, 16) for bx in range(0, width, 16)
                       for i in tile))


def psmt8_bytes(pixels: bytes, width: int, height: int) -> bytes:
    """Full PSMT8 texture hash input: logical block order, GS-swizzled bytes per block."""
    if width <= 0 or height <= 0 or width * height != len(pixels):
        raise ValueError("incorrect indexed pixel extent")
    if width < 16 or height < 16:
        # PCSX2 expands small textures and hashes only their actual index rows.
        return pixels
    if width % 16 or height % 16:
        raise ValueError("unaligned full PSMT8 texture")
    return bytes(pixels[i] for i in _block_order(width, height))


def load_dependencies():
    try:
        from PIL import Image
        import xxhash
    except ImportError as e:
        raise RuntimeError("install optional dependencies: python -m pip install "
                           "-r tools/requirements-textures.txt") from e
    return Image, xxhash


def original_keys(path: Path, Image, xxhash) -> list[TextureKey]:
    """Reconstruct supported full-texture PSMT8/PSMT8H keys from Wrench-style PNGs."""
    with Image.open(path) as image:
        width, height = image.size
        if not width or not height or width * height > MAX_PIXELS:
            raise ValueError("unsupported original dimensions")
        if image.format != "PNG":
            raise ValueError("original is not a PNG")
        if image.mode != "P":
            raise ValueError("original is not an indexed PNG; lost indices cannot be recovered")
        if width & (width - 1) or height & (height - 1):
            raise ValueError("non-power-of-two image needs region-aware extraction")
        if width > 32768 or height > 32768:
            raise ValueError("dimensions exceed the TEX0 field range")
        palette = image.getpalette("RGB")
        if palette is None or len(palette) != 768:
            raise ValueError("original needs all 256 palette entries")
        transparency = image.info.get("transparency")
        alphas = bytearray([255] * 256)
        if isinstance(transparency, bytes):
            alphas[:len(transparency)] = transparency
        elif isinstance(transparency, int):
            alphas[transparency] = 0
        if any(a != 255 and a % 2 for a in alphas):
            raise ValueError("palette alpha is not a Wrench-style doubled PS2 alpha")
        clut = bytearray()
        for i, alpha in enumerate(alphas):
            # Inverse of Wrench's PNG export. A matching key is not proof that
            # an original alpha above 0x80 survived that lossy conversion.
            clut.extend(palette[i * 3:i * 3 + 3])
            clut.append(128 if alpha == 255 else alpha // 2)
        pixels = image.tobytes()
    pal_hash = xxhash.xxh3_64_intdigest(clut)
    dimensions = (int(math.log2(width)) << 6) | (int(math.log2(height)) << 10)
    return [TextureKey(xxhash.xxh3_64_intdigest(psmt8_bytes(pixels, width, height)),
                       pal_hash, dimensions | 19),
            TextureKey(xxhash.xxh3_64_intdigest(pixels), pal_hash, dimensions | 27)]


def image_files(root: Path, suffix: str):
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() == suffix)


def input_error(error: Exception) -> str:
    # Pillow/OS exceptions can include absolute input paths. The separate path
    # field already identifies the file relative to its input root.
    return f"{type(error).__name__}: input could not be read" if isinstance(error, OSError) else str(error)


def match_pack(pack: Path, originals: Path | None = None, dumps: Path | None = None) -> dict:
    """Return metadata only. Keep every file/occurrence; never match a texture hash alone."""
    Image, xxhash = load_dependencies()
    index = defaultdict(list)
    skipped, errors = [], []
    source_count = 0
    if originals:
        for path in image_files(originals, ".png"):
            relative = path.relative_to(originals).as_posix()
            try:
                keys = original_keys(path, Image, xxhash)
            except ValueError as e:
                skipped.append({"path": relative, "reason": str(e)})
                continue
            except (OSError, Image.DecompressionBombError) as e:
                errors.append({"input": "originals", "path": relative, "reason": input_error(e)})
                continue
            source_count += 1
            for key in keys:
                index[key].append({"kind": "indexed_original", "path": relative})
    if dumps:
        for path in image_files(dumps, ".png"):
            relative = path.relative_to(dumps).as_posix()
            try:
                key = parse_key(path.stem)
                with Image.open(path) as image:
                    if image.format != "PNG":
                        raise ValueError("dump is not a PNG")
                    if image.width * image.height > MAX_PIXELS:
                        raise ValueError("unsupported dump dimensions")
                    expected = key.dump_dimensions()
                    if expected is not None and image.size != expected:
                        raise ValueError("dump dimensions disagree with its filename key")
                    image.verify()
            except ValueError as e:
                skipped.append({"input": "dumps", "path": relative, "reason": str(e)})
                continue
            except (OSError, Image.DecompressionBombError) as e:
                errors.append({"input": "dumps", "path": relative, "reason": input_error(e)})
                continue
            index[key].append({"kind": "pcsx2_dump_filename", "path": relative})
    rows = []
    for path in image_files(pack, ".dds"):
        row = {"path": path.relative_to(pack).as_posix(), "status": "unmatched", "sources": []}
        try:
            key = parse_key(path.stem)
        except ValueError as e:
            row.update(status="unsupported", reason=str(e))
            rows.append(row)
            continue
        row["key"] = key.fields()
        try:
            width, height = dds_dimensions(path)
        except (OSError, ValueError) as e:
            errors.append({"input": "pack", "path": row["path"], "reason": input_error(e)})
            row.update(status="invalid", reason=input_error(e))
            rows.append(row)
            continue
        row.update(width=width, height=height, sources=index.get(key, []))
        if row["sources"]:
            row["status"] = "key_match"
        rows.append(row)
    counts = {s: sum(r["status"] == s for r in rows)
              for s in ("key_match", "unmatched", "unsupported", "invalid")}
    return {"version": 1, "summary": {"replacements": len(rows), **counts,
                                     "indexed_originals": source_count, "invalid_inputs": len(errors)},
            "replacements": rows, "skipped_sources": skipped, "errors": errors}


def output_path(value: str) -> Path:
    path = Path(value)
    path = (path if path.is_absolute() else ROOT / path).resolve()
    if not path.is_relative_to((ROOT / "build").resolve()) or path.suffix.lower() != ".json":
        raise ValueError("output must be a JSON file inside this checkout's ignored build/")
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", required=True, type=Path, help="local extracted DDS replacement folder")
    parser.add_argument("--originals", type=Path, help="local extracted indexed original PNG folder")
    parser.add_argument("--dumps", type=Path, help="original PCSX2 PNG dump folder (filename-key evidence)")
    parser.add_argument("--output", default="build/texture-matches.json")
    parser.add_argument("--overwrite", action="store_true", help="replace an existing generated JSON report")
    args = parser.parse_args(argv)
    if not args.originals and not args.dumps:
        parser.error("provide --originals, --dumps, or both")
    for path in (args.pack, args.originals, args.dumps):
        if path is not None and not path.is_dir():
            parser.error(f"input is not a directory: {path}")
    try:
        output = output_path(args.output)
        if output.exists() and not args.overwrite:
            parser.error("output already exists; choose another name or use --overwrite")
        report = match_pack(args.pack, args.originals, args.dumps)
        if not report["summary"]["replacements"]:
            raise ValueError("no DDS replacements found in --pack")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except (OSError, RuntimeError, ValueError) as e:
        parser.exit(2, f"{e}\n")
    s = report["summary"]
    print(f"{s['key_match']} / {s['replacements']} replacement keys matched; "
          f"{s['invalid_inputs']} invalid inputs; {output.relative_to(ROOT)}")
    return 2 if s["invalid_inputs"] else 0


if __name__ == "__main__":
    sys.exit(main())
