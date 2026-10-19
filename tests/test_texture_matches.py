"""Synthetic texture correspondence cases; no game data or stored image fixtures."""
import contextlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import texture_matches as tm

try:
    Image, xxhash = tm.load_dependencies()
    HAS_IMAGES = True
except RuntimeError:
    HAS_IMAGES = False


class FilenameKeys(unittest.TestCase):
    def test_legacy_tcc_only_is_ignored(self):
        self.assertEqual(tm.parse_key("123-456-00005553"), tm.parse_key("123-456-00001553"))
        self.assertEqual(tm.parse_key("123-456-00001553"),
                         tm.parse_key("0000000000000123-0000000000000456-00001553"))
        self.assertNotEqual(tm.parse_key("123-456-00001553"), tm.parse_key("123-457-00001553"))
        self.assertNotEqual(tm.parse_key("123-456-00001553"), tm.parse_key("123-456-00001593"))

    def test_case_region_and_mip_are_preserved(self):
        self.assertEqual(tm.parse_key("AB-CD-r32x16-00001553-mip2"),
                         tm.parse_key("ab-cd-r32x16-00001553-mip2"))
        self.assertNotEqual(tm.parse_key("ab-cd-r32x16-00001553"),
                            tm.parse_key("ab-cd-r16x32-00001553"))
        self.assertNotEqual(tm.parse_key("ab-cd-00001553-mip1"), tm.parse_key("ab-cd-00001553"))
        self.assertEqual(tm.parse_key("ab-cd-r12345678-00001553").region, "r12345678")

    def test_nonpaletted_key_and_bad_names(self):
        self.assertIsNone(tm.parse_key("ab-00001500").palette)
        for text in ("texture", "ab-cd-1553", "ab-cd-00001553-extra", "ab-cd-r0x4-00001553"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                tm.parse_key(text)

    def test_output_is_confined_to_ignored_build(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(tm, "ROOT", Path(temp)):
            self.assertEqual(tm.output_path("build/matches.json"), Path(temp) / "build/matches.json")
            for path in ("progress/report.json", "build/../matches.json", "build/matches.png"):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    tm.output_path(path)


@unittest.skipUnless(HAS_IMAGES, "optional tools/requirements-textures.txt not installed")
class SyntheticImages(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pack = self.root / "pack"
        self.originals = self.root / "originals"
        self.dumps = self.root / "dumps"
        for path in (self.pack, self.originals, self.dumps):
            path.mkdir()
        self.rgb = bytes(v for i in range(256) for v in (i, i * 7 % 256, 255 - i))
        self.alpha = bytes(i % 129 for i in range(256))
        self.clut = bytes(v for i in range(256) for v in (*self.rgb[i * 3:i * 3 + 3], self.alpha[i]))
        self.png_alpha = bytes(min(255, a * 2) for a in self.alpha)
        self.pal_hash = xxhash.xxh3_64_intdigest(self.clut)
        # Independent oracle: bytes(range(256)) through PCSX2 columnTable8,
        # not through the implementation under test. Both fixtures are synthetic.
        self.key = tm.TextureKey(int("a96752d23fecbb61", 16), self.pal_hash, 19 | 4 << 6 | 4 << 10)

    def png(self, path=None, pixels=None, size=(16, 16), palette=None):
        path = path or self.originals / "synthetic.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.frombytes("P", size, pixels if pixels is not None else bytes(range(256)))
        image.putpalette(self.rgb if palette is None else palette)
        image.save(path, transparency=self.png_alpha)
        return path

    def dds(self, key=None, name=None):
        key = key or self.key
        name = name or (f"{key.texture:016x}-{key.palette:016x}-{key.bits | 0x4000:08x}.dds")
        path = self.pack / name
        path.parent.mkdir(parents=True, exist_ok=True)
        # Header-only synthetic DDS: the tool inventories headers, not DDS pixels.
        header = bytearray(128)
        header[:4] = b"DDS "
        struct.pack_into("<I", header, 4, 124)
        struct.pack_into("<II", header, 12, 64, 64)
        struct.pack_into("<I", header, 76, 32)
        path.write_bytes(header)
        return path

    def test_reference_swizzle_hash_and_palette_inverse(self):
        path = self.png()
        self.assertIn(self.key, tm.original_keys(path, Image, xxhash))
        self.assertEqual(xxhash.xxh3_64_hexdigest(tm.psmt8_bytes(bytes(range(256)), 16, 16)),
                         "a96752d23fecbb61")
        self.assertEqual(tm.psmt8_bytes(bytes(range(64)), 8, 8), bytes(range(64)))

    def test_complete_join_and_shared_occurrences(self):
        self.png(self.originals / "level-a" / "material.png")
        self.png(self.originals / "level-b" / "material.png")
        self.dds()
        report = tm.match_pack(self.pack, self.originals)
        row = report["replacements"][0]
        self.assertEqual(row["status"], "key_match")
        self.assertEqual([s["path"] for s in row["sources"]],
                         ["level-a/material.png", "level-b/material.png"])
        self.assertEqual(report["summary"]["key_match"], 1)
        self.assertNotIn(str(self.root), json.dumps(report))

    def test_wrong_palette_does_not_match_same_texture_hash(self):
        self.png()
        self.dds(tm.TextureKey(self.key.texture, self.pal_hash ^ 1, self.key.bits))
        self.assertEqual(tm.match_pack(self.pack, self.originals)["summary"]["key_match"], 0)

    def test_one_changed_index_does_not_match(self):
        self.png(pixels=bytes([1]) + bytes(range(1, 256)))
        self.dds()
        self.assertEqual(tm.match_pack(self.pack, self.originals)["summary"]["key_match"], 0)

    def test_psmt8h_equal_bytes_with_wrong_dimensions_do_not_match(self):
        pixels = bytes(range(256)) * 2
        self.png(pixels=pixels, size=(16, 32))
        tex = xxhash.xxh3_64_intdigest(pixels)
        self.dds(tm.TextureKey(tex, self.pal_hash, 27 | 5 << 6 | 4 << 10))
        self.assertEqual(tm.match_pack(self.pack, self.originals)["summary"]["key_match"], 0)

    def test_duplicate_replacement_keys_are_not_overwritten(self):
        self.png()
        self.dds()
        self.dds(name=f"UI/{self.key.texture:x}-{self.pal_hash:x}-{self.key.bits:08x}.dds")
        report = tm.match_pack(self.pack, self.originals)
        self.assertEqual(report["summary"]["replacements"], 2)
        self.assertEqual(report["summary"]["key_match"], 2)

    def test_region_and_mip_match_only_dump_filename_key(self):
        self.png()
        name = f"{self.key.texture:x}-{self.pal_hash:x}-r16x16-{self.key.bits:08x}-mip1"
        self.dds(name=name + ".dds")
        self.assertEqual(tm.match_pack(self.pack, self.originals)["summary"]["key_match"], 0)
        Image.new("RGBA", (8, 8), (1, 2, 3, 255)).save(self.dumps / (name + ".png"))
        row = tm.match_pack(self.pack, self.originals, self.dumps)["replacements"][0]
        self.assertEqual(row["status"], "key_match")
        self.assertEqual([s["kind"] for s in row["sources"]], ["pcsx2_dump_filename"])

    def test_short_and_padded_hash_names_join_in_both_directions(self):
        Image.new("RGBA", (16, 16)).save(self.dumps / "1-2-00001113.png")
        self.dds(tm.TextureKey(1, 2, 0x1113))
        self.assertEqual(tm.match_pack(self.pack, dumps=self.dumps)["summary"]["key_match"], 1)

    def test_dump_with_inconsistent_dimensions_is_not_matched(self):
        key = tm.TextureKey(1, 2, 0x1113)
        self.dds(key)
        Image.new("RGBA", (8, 8)).save(self.dumps / "1-2-00001113.png")
        report = tm.match_pack(self.pack, dumps=self.dumps)
        self.assertEqual(report["summary"]["key_match"], 0)
        self.assertIn("dimensions", report["skipped_sources"][0]["reason"])

    def test_noninvertible_palette_alpha_is_not_guessed(self):
        path = self.png()
        with Image.open(path) as image:
            image.save(path.with_name("odd.png"), transparency=bytes([1]) + self.png_alpha[1:])
        path.unlink()
        self.dds()
        report = tm.match_pack(self.pack, self.originals)
        self.assertEqual(report["summary"]["key_match"], 0)
        self.assertIn("alpha", report["skipped_sources"][0]["reason"])

    def test_rgba_original_and_unknown_pack_name_are_explicitly_unsupported(self):
        Image.new("RGBA", (16, 16)).save(self.originals / "lost-indices.png")
        self.dds(name="unknown.dds")
        report = tm.match_pack(self.pack, self.originals)
        self.assertEqual(report["summary"]["unsupported"], 1)
        self.assertIn("not an indexed", report["skipped_sources"][0]["reason"])

    def test_truncated_dds_is_not_a_match(self):
        self.png()
        self.dds().write_bytes(b"DDS ")
        report = tm.match_pack(self.pack, self.originals)
        self.assertEqual(report["summary"]["key_match"], 0)
        self.assertEqual(report["summary"]["invalid"], 1)

    def test_cli_reports_corruption_and_protects_existing_output(self):
        self.dds()
        (self.originals / "broken.png").write_bytes(b"not an image")
        args = ["--pack", str(self.pack), "--originals", str(self.originals)]
        with patch.object(tm, "ROOT", self.root), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(tm.main(args), 2)
            path = self.root / "build/texture-matches.json"
            self.assertEqual(json.loads(path.read_text())["summary"]["invalid_inputs"], 1)
            self.assertNotIn(str(self.root), path.read_text())
            before = path.read_bytes()
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                tm.main(args)
            self.assertEqual(path.read_bytes(), before)

    def test_cli_rejects_empty_pack_without_writing_a_report(self):
        self.png()
        with patch.object(tm, "ROOT", self.root), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as failure:
                tm.main(["--pack", str(self.pack), "--originals", str(self.originals)])
        self.assertEqual(failure.exception.code, 2)
        self.assertFalse((self.root / "build/texture-matches.json").exists())


if __name__ == "__main__":
    unittest.main()
