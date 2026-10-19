# Credits

This file records every outside project or person whose work this repository
uses, and what was used. Credit here is attribution only: it never adds
matching credit, and nothing listed is evidence for a match. The only evidence
is compiler output that compares byte for byte against the pinned executable.

Add a row for every item taken from an outside source, at the time it is taken,
with the source commit and the repository file it informed.

## Texture correspondence tooling

| Source and reviewed revision | Used for | Where |
| --- | --- | --- |
| [PCSX2](https://github.com/PCSX2/pcsx2), GPL-3.0-or-later, `d983b2b0665c40acb0455433eb656eebcb9efaf2` (`pcsx2/GS/GSTables.cpp`), and `091ab68708a555198d80a7216965481c7ddd0d98` (`GSTextureCache.cpp`, `GSTextureReplacements.cpp`) | PSMT8 block-byte ordering expressed as bit addressing; XXH3 hash input rules; filename keys and retired TCC-bit normalization | `tools/texture_matches.py`, synthetic swizzle oracle in `tests/test_texture_matches.py`, `docs/TEXTURE-MATCHING.md` |
| [Wrench](https://github.com/chaoticgd/wrench), GPL-3.0-or-later, `c57c17147fefcdec0631918d2a5875f7e24ec0e9` (`src/core/texture.cpp`) | Indexed PNG palette/alpha export convention, including the loss at alpha values above `0x80` | `tools/texture_matches.py`, `docs/TEXTURE-MATCHING.md` |
| [OpenRAC RAC1](https://github.com/OpenRAC/rac1-decomp), `6a72939bafff11b28fee52fa6e2099c6fb684ea9` (`docs/ASSETS.md`) | Documentation reference for structural asset identities and original-disc extraction; no decoder code copied | `docs/TEXTURE-MATCHING.md` |

No textures, pixel dumps, pack keys from real images, or generated asset correspondence tables
are included with this tooling. Test images and DDS headers are constructed synthetically at run time.

## Promises — RC2-Going-Decompiled

- Project: [Promises/RC2-Going-Decompiled](https://github.com/Promises/RC2-Going-Decompiled)
  (commits are authored under the name Henning Berge)
- Reviewed revision: `855deaff0eed040190198f83ed5fa7b871f52efb`
- Target of that project: Going Commando USA v2.00 and EU v1.00, not this
  repository's USA v1.01 target. Its addresses, sources and proofs are leads
  here until re-measured against `config/target.json`.
- Licence: the repository carries no `LICENSE` file at the reviewed revision.
  The initial gap-report PR copied no source. Subsequent tooling contributions
  import the reference helpers below under their upstream GPL-2.0 licence.
- Permission: the maintainer reports that the author agreed to reuse. The
  author's own approval on the pull request that introduced this file is the
  record; the scope and licence of any later adoption are to be stated in the
  row that adopts it.

### What was taken

| Item | Used for | Where |
| --- | --- | --- |
| Reference shell/AWK/sed helpers, once in `tools/ee/` | Experimental reference only; removed when the build was rewritten (2026-10-11) | contributor import history in PR #135; upstream licence revision `f134130e8e979843da090f89109a480b773bc2e3` |
| v2.00/EU symbol maps and derived name hints | Exploratory naming with region-specific addresses | `symbol_addrs/` and `config/datamine/`; naming adds no match credit |
| Gap comparison of their public tree against this repository | Listing leads we do not yet have | docs/PROMISES-GAP-REPORT.md |

Anything adopted later from this project is added to the table above, with the
source file and commit, in the same change that adopts it.

## Made in Slovakia — Ratchet & Clank PCSX2 cheat codes

[Made-in-Slovakia/rac](https://github.com/Made-in-Slovakia/rac) is credited by
the Promises project for its first global-naming anchors (v2.00 addresses).
It is listed here only because the Promises leads below depend on it. Nothing
from it is used in this repository.

## Lombyte (the NTSC decomp)

- The patch stack for the game compiler (`tools/compiler/patches/`, `sce-991111b`, MIT) and the
  recipe for the SDK compiler (`tools/compiler/sdk/build.py`, adapted from
  `scripts/build-patched-toolchain.py`, MIT, Mateusz Kłysz).
