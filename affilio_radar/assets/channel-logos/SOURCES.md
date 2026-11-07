# Channel logo assets — provenance and handling

All four files are bundled and loaded from disk. Runtime rendering has no network dependency.

| File | Source | Source blob SHA | License |
|---|---|---|---|
| `telegram.svg` | [Simple Icons](https://github.com/simple-icons/simple-icons/blob/develop/icons/telegram.svg) | `c46b0ed7098557205510d115000c08cb83af9106` | CC0 1.0 |
| `youtube.svg` | [Simple Icons](https://github.com/simple-icons/simple-icons/blob/develop/icons/youtube.svg) | `0492366a2be42c6f0372a64b8c6f4f6b2cb660f7` | CC0 1.0 |
| `bale.svg` | [Persian Labs Icons](https://github.com/persianlabs/icons/blob/main/packages/icons/assets/social-media/color/bale.svg) | `7fb59b7e289d3d6191fa82b18ed4db6622f78057` | MIT |
| `rubika.svg` | [Persian Labs Icons](https://github.com/persianlabs/icons/blob/main/packages/icons/assets/social-media/color/rubika.svg) | `caca73fcfbcdcf3862e5f9e076b92aeb9ebf7703` | MIT |

Source revisions:
- Persian Labs Icons: `8fb1e0c334fc3c0f20ad730fbfaeb9f3e72d0e50`
- Simple Icons: SVG blobs recorded above; licensing text is in `THIRD_PARTY_LICENSES.md`.

Official brand references used for visual cross-checking:
- Bale: https://bale.ai
- Rubika logo guidance and downloads: https://rubika.ir/logo
- Telegram: https://telegram.org/press
- YouTube logo and icon guidance: https://brand.youtube/youtube-logo

The Bale and Rubika artwork is sourced from the Persian Labs icon collection, not downloaded from the platforms' official brand packages. It was selected because its full-color app marks match the recognizable current symbols. Telegram and YouTube vectors come from Simple Icons; the original paths are retained and rendered with the familiar two-tone brand colors.

Only proportional antialiased downscaling is performed. Do not stretch, redraw, recolor, remove details, or fetch replacements at runtime. CC0/MIT copyright permissions do not transfer the platform owners' trademarks or imply endorsement or affiliation.
