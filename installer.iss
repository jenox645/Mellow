#define AppName "MellowDLP"
#define AppVersion "2.0"
#define AppPublisher "MellowDLP"
#define AppExeName "MellowDLP.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://github.com/mellowdlp
AppSupportURL=https://github.com/mellowdlp
AppUpdatesURL=https://github.com/mellowdlp
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
OutputDir=dist
OutputBaseFilename=MellowDLP_Setup
SetupIconFile=assets\mellow_round.ico
WizardImageFile=assets\wizard_large_v2.bmp
WizardSmallImageFile=assets\wizard_small_v2.bmp
WizardImageStretch=yes
WizardStyle=modern
Compression=lzma2/ultra64
SolidCompression=yes
DisableWelcomePage=no
DisableDirPage=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french";  MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}";  Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if not FileExists(ExpandConstant('{sys}\ffmpeg.exe')) then
      MsgBox(
        'MellowDLP is installed.' + #13#10 + #13#10 +
        'FFmpeg was not detected on your system.' + #13#10 +
        'FFmpeg is required for:' + #13#10 +
        '  - Embedding thumbnails into files' + #13#10 +
        '  - Embedding subtitles' + #13#10 +
        '  - SponsorBlock (sponsor segment removal)' + #13#10 + #13#10 +
        'Install FFmpeg by running this in Command Prompt:' + #13#10 +
        '    winget install ffmpeg' + #13#10 + #13#10 +
        'Then restart MellowDLP.',
        mbInformation, MB_OK);
  end;
end;
