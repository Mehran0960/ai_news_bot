# OfferChin video soundtrack

## Production path

- Product Shorts use the checked-in `affilio_radar/offerchin_audio.py` generator. It synthesizes a deterministic 12-second stereo funk/nu-disco bed in Python; it does not fetch a recording, SoundFont, or external audio asset at render time.
- `affilio_radar/short_video.py` mixes that soundtrack into the MP4, normalizes it to an integrated target of -16 LUFS with a -1.5 dBTP ceiling, and applies short fade-in/fade-out edges.
- Video duration remains capped at 12 seconds. The audio renderer follows the requested duration and the video is muxed with AAC audio.

## Selected private preview

The private fuse-box MP3 in the local review bundle is a SoundFont-rendered preview. Its build script identifies `TimGM6mb.sf2` as the source bank; MuseScore's SoundFont documentation lists TimGM6mb under GNU GPL v2. The preview MP3 and the SoundFont itself are not required by the production renderer and are not copied into the repository by this change. Do not treat the preview asset as commercially cleared solely because it is an MP3; keep the deterministic, SoundFont-free project generator in production unless the exact preview's provenance and use rights are separately approved.

References:
- MuseScore SoundFonts: https://musescore.org/en/handbook/2/soundfonts-and-sfz-files
- Debian TimGM6mb package copyright/licence: https://sources.debian.org/copyright/license/timgm6mb-soundfont/

## Validation

The video unit tests verify that the FFmpeg command normalizes the project soundtrack, fades both edges, maps the generated audio stream, and keeps a 12-second / 24-fps cut (288 frames). A separate smoke test performs a real MP4 encode and decodes it again with FFmpeg, checking that both audio and video streams exist and the duration is 12 seconds. No public YouTube or Aparat upload is part of these tests.
