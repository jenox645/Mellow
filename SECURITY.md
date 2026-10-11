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
  JSON for them (a CSRF guard), so a web page you visit can't drive it. It also refuses
  every request a browser marks as coming from another site (`Sec-Fetch-Site: cross-site`)
  and tells browsers no other origin may embed or frame its answers
  (`Cross-Origin-Resource-Policy`, `frame-ancestors 'none'`): the vault serves pictures and
  videos by path, and a page you visit must not be able to show them, probe for them or
  make a thumbnail request run ffmpeg.

## Checking a release

Every release is built and published by `.github/workflows/release.yml`, never by hand, and
each file has a signed [build provenance attestation](https://docs.github.com/en/actions/security-for-github-actions/using-artifact-attestations/using-artifact-attestations-to-establish-provenance-for-builds)
(from 2.9.0 on):

```
gh attestation verify MellowDLP-2.9.0-windows-setup.exe --repo jenox645/Mellow
```

It names the commit and the workflow run that built the file. `SHA256SUMS.txt` comes from the
same release as the files, so the in-app updater's checksum check catches a broken or swapped
download, not a compromised GitHub account; the attestation is signed by GitHub Actions'
identity, so a file uploaded by hand wouldn't have one. The releases aren't code-signed yet.
