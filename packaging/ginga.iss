; Inno Setup script for ginga wallpaper: per-user install, no admin rights.
; Built by scripts/build_exe.py, which passes the paths and the version:
;   ISCC /DAppVersion=2.1.0 /DSourceDir=...\dist\ginga /DOutputDir=...\dist
;        /DIconFile=...\build\ginga.ico packaging\ginga.iss

#ifndef AppVersion
  #error AppVersion must be defined (/DAppVersion=x.y.z)
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\ginga"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif
#ifndef IconFile
  #define IconFile "..\build\ginga.ico"
#endif

#define AppName "ginga wallpaper"
#define AppExe "ginga.exe"
; Must match autostart.RUN_KEY / VALUE_NAME and __main__.MUTEX_NAME.
#define RunKey "Software\Microsoft\Windows\CurrentVersion\Run"
#define RunValue "ginga wallpaper"

[Setup]
; Fixed AppId: upgrades replace the previous install instead of adding another.
AppId={{7B3E2A91-5C4D-4F8E-9A61-2D0C8B4F1E37}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Felipe Fernandes
AppPublisherURL=https://github.com/felipefernandes/ginga-wallpaper
AppSupportURL=https://github.com/felipefernandes/ginga-wallpaper/issues
AppUpdatesURL=https://github.com/felipefernandes/ginga-wallpaper/releases
VersionInfoVersion={#AppVersion}
; Per-user: {autopf} resolves to %LOCALAPPDATA%\Programs with lowest privileges.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=
DefaultDirName={autopf}\ginga
DisableDirPage=auto
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
SetupIconFile={#IconFile}
OutputDir={#OutputDir}
OutputBaseFilename=ginga-{#AppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
; The app holds this mutex while running: setup/uninstall ask to close it.
AppMutex=Local\ginga-wallpaper
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
brazilianportuguese.AutostartTask=Iniciar junto com o Windows
english.AutostartTask=Start with Windows
brazilianportuguese.StartupGroup=Inicialização:
english.StartupGroup=Startup:

[Tasks]
Name: "autostart"; Description: "{cm:AutostartTask}"; GroupDescription: "{cm:StartupGroup}"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Upgrades: wipe the old bundle first so stale libraries never mix with new ones.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Same value the app's Settings window writes, so both stay in sync.
Root: HKCU; Subkey: "{#RunKey}"; ValueType: string; ValueName: "{#RunValue}"; ValueData: """{app}\{#AppExe}"""; Tasks: autostart

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
{ An unticked "autostart" task leaves the Run key alone: the Settings window owns
  that choice after install. }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  { The Settings window may have enabled autostart after install: always remove it.
    User data in %APPDATA%\ginga (config, log) is kept on purpose. }
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, '{#RunKey}', '{#RunValue}');
end;
