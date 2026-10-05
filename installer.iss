; AppVersion is normally injected by build_setup.py via /DAppVersion=x.y.z
#ifndef AppVersion
  #define AppVersion "2.5.0"
#endif

[Setup]
AppName=MellowDLP
AppVersion={#AppVersion}
DefaultDirName={autopf}\MellowDLP
SetupIconFile=assets\mellow.ico
WizardImageFile=assets\wizard_large.bmp
WizardSmallImageFile=assets\wizard_small.bmp
OutputDir=dist
OutputBaseFilename=MellowDLP_Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
DisableDirPage=no
DisableProgramGroupPage=yes
DisableWelcomePage=no
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
