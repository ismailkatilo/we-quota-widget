#define MyAppName "WE Quota Widget"
#define MyAppVersion "0.9.6-beta"
#define MyAppPublisher "KatiloWorks"
#define MyAppExeName "WE Widget.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://github.com
DefaultDirName={localappdata}\WE Widget
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=.
OutputBaseFilename=WE_Widget_v0.9.6-beta
SetupIconFile=app_icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\app_icon.ico
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startupregistry"; Description: "Start automatically with Windows"; GroupDescription: "Windows Startup:"; Flags: checkedonce
Name: "desktopicon";     Description: "Create a desktop shortcut";                GroupDescription: "Additional shortcuts:"; Flags: checkedonce

[Files]
; Pointing to the default PyInstaller output and renaming it to match MyAppExeName
Source: "dist\we_quota_widget.exe"; DestDir: "{app}"; DestName: "{#MyAppExeName}"; Flags: ignoreversion
Source: "app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: startupregistry

[UninstallDelete]
; Clean up the settings saved in the Documents folder
Type: filesandordirs; Name: "{userdocs}\WE Widget"
; Clean up the installation directory
Type: filesandordirs; Name: "{app}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch WE Quota Widget now"; Flags: nowait postinstall skipifsilent