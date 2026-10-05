### Download

| File | For |
|---|---|
| [MellowDLP-{version}-windows-setup.exe](https://github.com/{repo}/releases/download/{tag}/MellowDLP-{version}-windows-setup.exe) | **Windows** installer (recommended) |
| [MellowDLP-{version}-windows-portable.exe](https://github.com/{repo}/releases/download/{tag}/MellowDLP-{version}-windows-portable.exe) | Windows, no install: one exe you keep anywhere |
| [MellowDLP-{version}-x86_64.AppImage](https://github.com/{repo}/releases/download/{tag}/MellowDLP-{version}-x86_64.AppImage) | **Linux**, any distro: `chmod +x` it and run it |
| [MellowDLP-{version}-linux-x86_64](https://github.com/{repo}/releases/download/{tag}/MellowDLP-{version}-linux-x86_64) | Linux, a plain binary |

**Already using MellowDLP?** No need to download: click UPDATE in its status bar.

Windows may say "Windows protected your PC": the exe isn't code-signed. Click **More info → Run anyway**. To check a file first, compare `certutil -hashfile <file> SHA256` (Linux: `sha256sum -c SHA256SUMS.txt --ignore-missing`) with `SHA256SUMS.txt`.

No ffmpeg yet? The app offers **GET FFMPEG** at its first start.
