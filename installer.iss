[Setup]
AppName=MellowDLP
AppVersion=2.0
DefaultDirName={autopf}\MellowDLP
SetupIconFile=assets\mellow.ico
WizardImageFile=assets\wizard_large.bmp
WizardSmallImageFile=assets\wizard_small.bmp
OutputDir=dist
OutputBaseFilename=MellowDLP_Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=classic
PrivilegesRequired=lowest
DisableDirPage=no
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\MellowDLP.exe

[Tasks]
Name: desktopicon; Description: "Create desktop shortcut"

[Files]
Source: "dist\MellowDLP.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\MellowDLP"; Filename: "{app}\MellowDLP.exe"; IconFilename: "{app}\MellowDLP.exe"
Name: "{autodesktop}\MellowDLP"; Filename: "{app}\MellowDLP.exe"; Tasks: desktopicon; IconFilename: "{app}\MellowDLP.exe"

[Run]
Filename: "{app}\MellowDLP.exe"; Description: "Launch MellowDLP"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    if not FileExists(ExpandConstant('{sys}\ffmpeg.exe')) then
      MsgBox(
        'FFmpeg not found. Install it with:' + #13#10 +
        '    winget install ffmpeg' + #13#10 + #13#10 +
        'Required for thumbnails, subtitles and SponsorBlock.',
        mbInformation, MB_OK);
end;
