# Security

## Reporting a problem

Please report security problems privately, not as a public issue: on this repository's
**Security** tab, choose **Report a vulnerability**. Say what an attacker could do and how,
and the MellowDLP version you checked.

Only the newest release gets fixes: every copy updates itself to it.

## What matters most

MellowDLP downloads and runs code, so these are the parts worth a close look:

- **App updates** (`mellow/app_update.py`): downloads a release asset from this repository
  and installs it. The file must match the release's `SHA256SUMS.txt`, and downloads are only
  taken from this repository's releases.
- **yt-dlp updates** (`mellow/ytdlp_update.py`): yt-dlp's official release, checked against
  its `SHA2-256SUMS`.
- **GET FFMPEG** (`mellow/ffmpeg_install.py`): a [BtbN](https://github.com/BtbN/FFmpeg-Builds)
  build checked against its `checksums.sha256`; only `ffmpeg` and `ffprobe` are extracted,
  to fixed names.
- **The local server**: Flask on `127.0.0.1` only. It answers only requests addressed to
  localhost (against DNS rebinding), refuses changes from another origin, and requires
  JSON for them (a CSRF guard), so a web page you visit can't drive it.

The checksums come from the same place as the files, so they catch broken or swapped
downloads, not a compromised GitHub account. The releases aren't code-signed yet.
