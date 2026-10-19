# Matching texture replacements to original resources

`tools/texture_matches.py` joins a local PCSX2 DDS pack to original textures extracted
from your disc, or to original PCSX2 PNG dumps. It writes metadata only to ignored
`build/`. Neither the pack, original images, generated correspondence files nor thumbnails
belong in Git. This tool does not change the game build or its progress report.

## Prepare local inputs

Use your own legally acquired USA v1.01 disc and verify the ISO identity in
[BUILDING.md](BUILDING.md). This tool reads extracted files; it does not authenticate an ISO,
download a pack or install textures in an emulator. Obtain the complete qualified build
environment before making a matching-code contribution.

Install the optional image-analysis dependencies in your existing Python environment:

```sh
python -m pip install -r tools/requirements-textures.txt
```

The normal compiler/build commands do not need these packages. The synthetic image tests
skip when they are absent; CI installs them so those tests actually run.

One source of indexed original PNGs is [Wrench](https://github.com/chaoticgd/wrench).
With your own Wrench installation, extract into an ignored directory:

```sh
wrenchbuild unpack baserom/SCUS_972.68.iso -o build/texture-inputs/originals
```

Wrench's paths retain useful level, class and material indices. Extract the HD pack yourself
into another local folder, such as `build/texture-inputs/pack`. Keep any archive and its
extracted contents private too. Point the tool at the containing directories; it searches
PNG/DDS files recursively and retains every occurrence of a shared texture.

## Run the comparison

```sh
python tools/texture_matches.py \
  --originals build/texture-inputs/originals \
  --pack build/texture-inputs/pack \
  --output build/texture-matches.json
```

You may supply `--dumps` as well, or instead of `--originals`:

```sh
python tools/texture_matches.py \
  --dumps build/texture-inputs/original-dumps \
  --pack build/texture-inputs/pack \
  --output build/texture-dump-matches.json
```

These must be dumps produced while running the original disc. Verify the active game and
edition in PCSX2. Start with a static menu: dumping during video playback produces many
frame images that are poor candidates for static resource identification. The tool does not
start or control PCSX2, modify its settings, or infer game identity from a folder name.

Output paths must be JSON files inside **this checkout's `build/`**, regardless of the working
directory. Existing reports are protected; use a new name or explicitly pass `--overwrite`.
Input directories are never written to. Paths inside the report are relative to their own
input roots, so it does not embed machine-specific absolute paths.

## Read the result

The report contains `version`, `summary`, `replacements`, `skipped_sources` and `errors`.
Every DDS has a record; duplicate replacement keys and multiple original occurrences are
preserved. Each matching source names its evidence kind:

| Evidence kind | What was compared |
| --- | --- |
| `indexed_original` | XXH3 of indexed pixels in the supported GS layout, the complete 256-entry palette, PSM and full-texture dimensions |
| `pcsx2_dump_filename` | The complete normalized PCSX2 filename key, plus dump dimensions when those can be decoded |

Replacement statuses are `key_match`, `unmatched`, `unsupported` (filename outside the
supported grammar), or `invalid` (bad DDS header). Invalid inputs are recorded and make the
command exit **2**, even though its diagnostic report is written. Unsupported originals are
listed with a reason. Unmatched files are an expected result, not an error. An empty pack or
invalid command line exits 2 without creating a new report.

**`key_match` means a correspondence of identifiers, not authentication of the replacement's
pixels or artistic quality.** DDS headers are inspected, not image payloads decoded. Dump
keys come from their filenames; renaming an arbitrary image cannot prove its origin. A
64-bit texture hash alone is insufficient, so the palette and other key fields are retained.
No perceptual similarity result is silently promoted to a match.

## Supported layouts and limits

- Full, power-of-two indexed PNGs with all 256 palette entries support **PSMT8** (16-by-16
  GS blocks, expanded index rows for smaller textures) and **PSMT8H** (expanded indices).
  RGBA originals have lost their palette indices and are explicitly skipped.
- Wrench exports PS2 alpha as doubled PNG alpha, saturating at 255. The inverse assumes
  saturated values were `0x80`; it cannot recover original values above `0x80`. Odd PNG alpha
  other than 255 is not accepted as this export convention. Preserve original binary palette
  data separately when exact alpha behavior matters for the port.
- The retired TCC bit is cleared just as PCSX2's `RemoveUnusedBits` does. Region and mip
  suffixes remain part of the key. Region/mip replacements are not guessed from a full
  original PNG; they can match an equivalent dump filename. Old packed-region strings are
  retained literally, without translating them to the newer `rWIDTHxHEIGHT` syntax.
- Wrench exports do not necessarily include every original mip or every HUD image. The tool
  neither invents missing mip pixels nor decodes additional archive formats. Supply separately
  extracted indexed originals if available; missing source coverage stays visible.
- An asset path identifies a resource occurrence, not its original artist filename or an EE
  loading/drawing function. A palette shared with another image does not establish ownership.
  Preserve all source occurrences when building a future native-port replacement resolver.

No result here adds matched C, matched game data or runtime-port progress. Any future port
loader must choose a resource identity and resolve sharing/ambiguities explicitly; this PR
only supplies the correspondence tool.

## Method and tests

The filename normalization and GS block ordering follow the
[PCSX2 implementation](https://github.com/PCSX2/pcsx2/tree/master/pcsx2/GS).
The alpha convention follows Wrench's `src/core/texture.cpp`.
OpenRAC RAC1's [asset-format documentation](https://github.com/OpenRAC/rac1-decomp/blob/main/docs/ASSETS.md)
explains the structure-first approach: original archive tables, material/texture indices and
class references establish resource identities; Wrench/Lombyte provide documented class
labels. This tool uses the extracted relative paths without importing RAC1 addresses or
assuming its disc layout applies to RAC2. Exact source revisions are in [CREDITS.md](../CREDITS.md).

```sh
python -m unittest discover -s tests -p test_texture_matches.py -v
```

Tests generate their indexed PNGs and DDS headers in temporary directories. They cover an
independent synthetic swizzle oracle, alpha recovery, wrong palettes/pixels/dimensions,
sharing, duplicate pack keys, legacy flags, region/mip isolation, corruption and output
protection. No game-derived image, filename key or generated correspondence is a fixture.
