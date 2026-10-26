; Compile through scripts/make-windows.ps1 using the shared release payload.
#ifndef PayloadDir
  #error PayloadDir is required
#endif
#ifndef AppVersion
  #error AppVersion is required
#endif
#ifndef Repository
  #error Repository is required
#endif
#define NumericVersion Copy(AppVersion, 1, Pos('-', AppVersion + '-') - 1)
#define ProductId "DayuanJiang.PecoFence"
#define ProductName "Nodra"
#define CurrentRunName "PecoFence"
#define LegacyRunName "openFence"
#define AppMutexNames "Local\PecoFence.SingleInstance,Local\openFence.SingleInstance"
; Integration tests compile this same script with an isolated identity. The public
; packaging command never sets TestIdentity; test installers must never be shipped.
#ifdef TestIdentity
  #define ProductId "PecoFence.InstallerTest." + TestIdentity
  #define ProductName "Nodra Installer Test " + TestIdentity
  #define CurrentRunName ProductId
  #define LegacyRunName ProductId + ".legacy"
  #define AppMutexNames "Local\" + ProductId
#endif

[Setup]
AppId={#ProductId}
AppName={#ProductName}
AppVersion={#AppVersion}
VersionInfoVersion={#NumericVersion}
AppPublisher=Nodra Project
AppPublisherURL=https://github.com/{#Repository}
AppSupportURL=https://github.com/{#Repository}/issues
AppUpdatesURL=https://github.com/{#Repository}/releases
DefaultDirName={localappdata}\Programs\{#ProductName}
DefaultGroupName={#ProductName}
; Always offer the destination page: the user picks the default folder or types their own.
DisableDirPage=no
PrivilegesRequired=lowest
UsePreviousAppDir=yes
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.19045
SetupIconFile=..\..\crates\app\assets\pecofence.ico
UninstallDisplayIcon={app}\pecofence.exe
OutputBaseFilename=pecofence-v{#AppVersion}-x64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; No [Setup] AppMutex: it would abort with a dialog before the script can close a
; running app. InitializeSetup asks the app to leave through its own update-close
; path instead (silent for the updater, no prompt for the user), and waits for the
; instance mutex to be released before anything is removed or overwritten.
SetupMutex=Local\{#ProductId}.Setup
; The app/watchdog must restore desktop icons through their normal exit path.
CloseApplications=no
RestartApplications=no

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "zh_CN"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "zh_TW"; MessagesFile: "compiler:Languages\ChineseTraditional.isl"
Name: "ja"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "ko"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "pt_BR"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Explicit payload: never collect config, caches or arbitrary files from a checkout.
Source: "{#PayloadDir}\pecofence-watchdog.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\pecofence-cli.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\WebView2Loader.dll"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\LICENSE-WebView2Loader.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\THIRD-PARTY-LICENSES.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\UPGRADING.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PayloadDir}\SKILL.md"; DestDir: "{app}"; Flags: ignoreversion
; Last: an update aborted halfway (a file in use) keeps the old app, which offers it again.
Source: "{#PayloadDir}\pecofence.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#ProductName}"; Filename: "{app}\pecofence.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\{#ProductName}"; Filename: "{app}\pecofence.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\pecofence.exe"; Description: "{cm:LaunchProgram,{#ProductName}}"; Flags: nowait postinstall skipifsilent
; The in-app updater runs setup silently and has exited: start the new version.
Filename: "{app}\pecofence.exe"; Flags: nowait; Check: RestartAfterUpdate

[CustomMessages]
en.AlreadyInstalled=Nodra is already installed in %1. To install it in another folder, uninstall it first.
zh_CN.AlreadyInstalled=Nodra 已经装在 %1。想换个位置，请先卸载。
zh_TW.AlreadyInstalled=Nodra 已經安裝在 %1。想換個位置，請先解除安裝。
ja.AlreadyInstalled=Nodra はすでに %1 にインストールされています。別のフォルダーに入れるには、先にアンインストールしてください。
ko.AlreadyInstalled=Nodra가 이미 %1에 설치되어 있습니다. 다른 폴더에 설치하려면 먼저 제거하세요.
de.AlreadyInstalled=Nodra ist bereits in %1 installiert. Um es in einen anderen Ordner zu installieren, deinstalliere es zuerst.
fr.AlreadyInstalled=Nodra est déjà installé dans %1. Pour l'installer dans un autre dossier, désinstallez-le d'abord.
es.AlreadyInstalled=Nodra ya está instalado en %1. Para instalarlo en otra carpeta, desinstálalo primero.
pt_BR.AlreadyInstalled=O Nodra já está instalado em %1. Para instalá-lo em outra pasta, desinstale-o primeiro.
ru.AlreadyInstalled=Nodra уже установлен в %1. Чтобы установить его в другую папку, сначала удалите его.
en.InvalidDestination=This folder already contains other files. Choose an empty folder, or the folder that already contains Nodra.
zh_CN.InvalidDestination=这个文件夹里已经有别的文件了。请选一个空文件夹，或者原来放 Nodra 的文件夹。
zh_TW.InvalidDestination=這個資料夾裡已經有其他檔案。請選一個空資料夾，或原本放 Nodra 的資料夾。
ja.InvalidDestination=このフォルダーには別のファイルがあります。空のフォルダーか、Nodra が入っているフォルダーを選んでください。
ko.InvalidDestination=이 폴더에는 이미 다른 파일이 있습니다. 빈 폴더나 Nodra가 들어 있는 폴더를 선택하세요.
de.InvalidDestination=Dieser Ordner enthält bereits andere Dateien. Wähle einen leeren Ordner oder den Ordner, in dem Nodra schon liegt.
fr.InvalidDestination=Ce dossier contient déjà d'autres fichiers. Choisissez un dossier vide ou celui qui contient déjà Nodra.
es.InvalidDestination=Esta carpeta ya tiene otros archivos. Elige una carpeta vacía o la que ya contiene Nodra.
pt_BR.InvalidDestination=Esta pasta já tem outros arquivos. Escolha uma pasta vazia ou a que já contém o Nodra.
ru.InvalidDestination=В этой папке уже есть другие файлы. Выберите пустую папку или ту, где уже лежит Nodra.
en.NewerVersion=A newer version of Nodra is already installed. Uninstall it first to install this older version. Your settings and fences are kept.
zh_CN.NewerVersion=已经装了更新的 Nodra。要装这个旧版本，请先卸载。设置和栅栏都会保留。
zh_TW.NewerVersion=已經安裝了較新的 Nodra。要安裝這個舊版本，請先解除安裝。設定和圍欄都會保留。
ja.NewerVersion=新しいバージョンの Nodra がインストールされています。この古いバージョンを入れるには、先にアンインストールしてください。設定とフェンスは残ります。
ko.NewerVersion=더 최신 버전의 Nodra가 설치되어 있습니다. 이 이전 버전을 설치하려면 먼저 제거하세요. 설정과 펜스는 그대로 남습니다.
de.NewerVersion=Eine neuere Version von Nodra ist bereits installiert. Um diese ältere Version zu installieren, deinstalliere sie zuerst. Deine Einstellungen und Bereiche bleiben erhalten.
fr.NewerVersion=Une version plus récente de Nodra est déjà installée. Pour installer cette version plus ancienne, désinstallez-la d'abord. Vos réglages et vos groupes sont conservés.
es.NewerVersion=Ya hay una versión más reciente de Nodra instalada. Para instalar esta versión anterior, desinstálala primero. Tus ajustes y grupos se conservan.
pt_BR.NewerVersion=Uma versão mais recente do Nodra já está instalada. Para instalar esta versão anterior, desinstale-a primeiro. Suas configurações e grupos são mantidos.
ru.NewerVersion=Уже установлена более новая версия Nodra. Чтобы установить старую версию, сначала удалите новую. Настройки и области сохранятся.

[Code]
const
  UninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#ProductId}_is1';
  RunKey = 'Software\Microsoft\Windows\CurrentVersion\Run';
  ControlWindowClass = 'PecoFence.Control';
  WM_QUERYENDSESSION = $0011;
  WM_ENDSESSION = $0016;
  ENDSESSION_CLOSEAPP = $00000001;

var
  Updating, Installed, OldRemoved: Boolean;

function OpenProcess(Access: DWORD; Inherit: BOOL; Pid: DWORD): THandle;
  external 'OpenProcess@kernel32.dll stdcall';
function WaitForSingleObject(Handle: THandle; Milliseconds: DWORD): DWORD;
  external 'WaitForSingleObject@kernel32.dll stdcall';
function CloseHandle(Handle: THandle): BOOL;
  external 'CloseHandle@kernel32.dll stdcall';
procedure Sleep(Milliseconds: DWORD);
  external 'Sleep@kernel32.dll stdcall';
function FindWindowW(ClassName: String; WindowName: String): THandle;
  external 'FindWindowW@user32.dll stdcall';
function PostMessageW(Wnd: THandle; Msg: DWORD; WParam: DWORD; LParam: DWORD): BOOL;
  external 'PostMessageW@user32.dll stdcall';

{ /UPDATE=<pid>,<pid>...: started by Nodra's updater, which exits right away. Wait, 30 s
  at most in all, until it, its watchdogs and its instance lock are gone, so no file is
  in use. Every pid is opened first, so one that exits early cannot be reused by another
  process meanwhile. }
{ Asks a running instance to leave through its own update-close path, the same one
  Restart Manager triggers: WM_QUERYENDSESSION saves the config and shows the real
  desktop icons, WM_ENDSESSION with ENDSESSION_CLOSEAPP then quits as the tray's
  exit item does. The watchdog sees the clean-exit marker gone and exits without
  restarting the old build. Afterwards the instance mutex must be free. }
procedure CloseRunningAppGracefully;
var
  Wnd: THandle;
  I: Integer;
begin
  if CheckForMutexes('{#AppMutexNames}') then begin
    Wnd := FindWindowW(ControlWindowClass, 'Nodra');
    if Wnd = 0 then
      Wnd := FindWindowW(ControlWindowClass, 'PecoFence');
    if Wnd <> 0 then begin
      PostMessageW(Wnd, WM_QUERYENDSESSION, 0, 0);
      Sleep(800);
      PostMessageW(Wnd, WM_ENDSESSION, 1, ENDSESSION_CLOSEAPP);
      Log('asked the running app to close for the update');
    end;
    for I := 1 to 100 do begin
      if not CheckForMutexes('{#AppMutexNames}') then
        break;
      Sleep(100);
    end;
  end;
end;

function InitializeSetup: Boolean;
var
  Pids: String;
  Comma, Count, I, Round: Integer;
  Processes: array of THandle;
  Waiting: Boolean;
begin
  { Before anything else (and before any in-use file is touched): ask a running
    instance to leave through its own update-close path and wait for it. }
#ifndef TestIdentity
  CloseRunningAppGracefully;
#endif
  Result := True;
  Pids := ExpandConstant('{param:UPDATE|}');
  Updating := Pids <> '';
  Count := 0;
  while Pids <> '' do begin
    Comma := Pos(',', Pids);
    if Comma = 0 then
      Comma := Length(Pids) + 1;
    SetArrayLength(Processes, Count + 1);
    Processes[Count] := OpenProcess($00100000 { SYNCHRONIZE }, False, StrToIntDef(Copy(Pids, 1, Comma - 1), 0));
    if Processes[Count] <> 0 then
      Count := Count + 1;
    Delete(Pids, 1, Comma);
  end;
  if Updating then begin
    for Round := 0 to 300 do begin
      Waiting := CheckForMutexes('{#AppMutexNames}');
      for I := 0 to Count - 1 do
        if WaitForSingleObject(Processes[I], 0) <> 0 then
          Waiting := True;
      if not Waiting or (Round = 300) then begin
        Log(Format('Update: waited %d ms for Nodra to exit', [Round * 100]));
        Break;
      end;
      Sleep(100);
    end;
  end;
  for I := 0 to Count - 1 do
    CloseHandle(Processes[I]);
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    Installed := True;
end;

{ Test installers carry the real app: they log the restart instead of running it. }
function StartApp(const Executable: String): Boolean;
#ifndef TestIdentity
var
  Code: Integer;
#endif
begin
#ifdef TestIdentity
  Log('Test identity: would start ' + Executable);
  Result := False;
#else
  Result := ExecAsOriginalUser(Executable, '', '', SW_SHOWNORMAL, ewNoWait, Code);
#endif
end;

function RestartAfterUpdate: Boolean;
begin
  Result := Updating;
#ifdef TestIdentity
  if Result then
    StartApp(ExpandConstant('{app}\pecofence.exe'));
  Result := False;
#endif
end;

{ An update that failed or was cancelled must not leave the user without Nodra (unless it
  never exited: then it is still running). }
procedure DeinitializeSetup;
var
  PreviousDir: String;
begin
  if Updating and not Installed and not CheckForMutexes('{#AppMutexNames}') and
    RegQueryStringValue(HKCU, UninstallKey, 'InstallLocation', PreviousDir) and
    FileExists(AddBackslash(PreviousDir) + 'pecofence.exe') then
    StartApp(AddBackslash(PreviousDir) + 'pecofence.exe');
end;

function SameDirectory(const Left, Right: String): Boolean;
begin
  Result := CompareText(RemoveBackslashUnlessRoot(ExpandFileName(Left)),
    RemoveBackslashUnlessRoot(ExpandFileName(Right))) = 0;
end;

{ Uninstalls the previous release with its own unins000.exe, silently and without
  any user interaction, before this one is installed. The configuration lives
  outside the install folder and survives both. Returns True when the previous
  release was removed (its uninstall key is gone afterwards). }
function RemovePreviousRelease: Boolean;
var
  UninstCmd, PreviousVersion: String;
  PreviousNumber, NewNumber: Int64;
  ExitCode: Integer;
  Newer: Boolean;
begin
  Result := False;
  ExitCode := -1;
  if not RegQueryStringValue(HKCU, UninstallKey, 'UninstallString', UninstCmd) then begin
    Log('previous release: no UninstallString in the uninstall key');
    exit;
  end;
  if UninstCmd = '' then
    exit;
  { Strip the quotes UninstallString wraps the path in. Pos is unreliable on paths
    with non-ASCII characters, so peel the quotes off the ends by direct comparison. }
  if Copy(UninstCmd, 1, 1) = '"' then begin
    Delete(UninstCmd, 1, 1);
    while (UninstCmd <> '') and (Copy(UninstCmd, Length(UninstCmd), 1) = '"') do
      Delete(UninstCmd, Length(UninstCmd), 1);
  end;
  if (UninstCmd = '') or not FileExists(UninstCmd) then begin
    Log(Format('previous release: uninstaller not usable: %s', [UninstCmd]));
    exit;
  end;
  { Never uninstall a newer release to install an older one over it. }
  Newer := False;
  if RegQueryStringValue(HKCU, UninstallKey, 'DisplayVersion', PreviousVersion) then
    if StrToVersion(PreviousVersion, PreviousNumber) and
      StrToVersion('{#NumericVersion}', NewNumber) then
      Newer := ComparePackedVersion(PreviousNumber, NewNumber) > 0;
  if Newer then begin
    Log('a newer release is installed; not removing it');
    exit;
  end;
  Log(Format('removing the previous release with %s', [UninstCmd]));
  if Exec(UninstCmd, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_SHOWNORMAL,
    ewWaitUntilTerminated, ExitCode) then
    Result := ExitCode = 0;
  Sleep(500);
  Log(Format('previous-release uninstaller exit code: %d', [ExitCode]));
end;

function DirectoryHasEntries(const Path: String): Boolean;
var
  Entry: TFindRec;
begin
  Result := False;
  if FindFirst(AddBackslash(Path) + '*', Entry) then begin
    try
      repeat
        if (Entry.Name <> '.') and (Entry.Name <> '..') then begin
          Result := True;
          Break;
        end;
      until not FindNext(Entry);
    finally
      FindClose(Entry);
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  PreviousDir, PreviousVersion: String;
  PreviousNumber, NewNumber: Int64;
begin
  Result := '';
  OldRemoved := False;

#ifndef TestIdentity
  { A running instance would keep files and locks busy through both the old
    uninstaller and this install. }
  CloseRunningAppGracefully;
#endif
  OldRemoved := RemovePreviousRelease;

  { A registration whose folder was deleted by hand no longer pins the location. }
  if RegQueryStringValue(HKCU, UninstallKey, 'InstallLocation', PreviousDir) and
    DirExists(PreviousDir) then begin
    if not SameDirectory(PreviousDir, ExpandConstant('{app}')) then begin
      Result := FmtMessage(CustomMessage('AlreadyInstalled'), [RemoveBackslashUnlessRoot(PreviousDir)]);
      Exit;
    end;
    if RegQueryStringValue(HKCU, UninstallKey, 'DisplayVersion', PreviousVersion) then begin
      { Compare the numeric release version; prerelease suffixes do not affect ordering. }
      if Pos('-', PreviousVersion) > 0 then
        PreviousVersion := Copy(PreviousVersion, 1, Pos('-', PreviousVersion) - 1);
      if StrToVersion(PreviousVersion, PreviousNumber) and
        StrToVersion('{#NumericVersion}', NewNumber) then
        if ComparePackedVersion(PreviousNumber, NewNumber) > 0 then
          Result := CustomMessage('NewerVersion');
    end;
  end else if (not OldRemoved) and DirectoryHasEntries(ExpandConstant('{app}')) and
    not FileExists(ExpandConstant('{app}\pecofence.exe')) then
    { A folder the ZIP was extracted into is upgraded in place; unrelated files are not.
      After RemovePreviousRelease the emptied folder is the old install location, so a
      leftover unrelated file must not block the reinstall. }
    Result := CustomMessage('InvalidDestination');
end;

procedure RemoveOwnedStartupValue(const Name: String);
var
  Command, Executable: String;
begin
  Executable := ExpandConstant('{app}\pecofence.exe');
  if RegQueryStringValue(HKCU, RunKey, Name, Command) then
    if (CompareText(Trim(Command), Executable) = 0) or
      (CompareText(Trim(Command), '"' + Executable + '"') = 0) then
      RegDeleteValue(HKCU, RunKey, Name);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then begin
    RemoveOwnedStartupValue('{#CurrentRunName}');
    RemoveOwnedStartupValue('{#LegacyRunName}');
  end;
  if CurUninstallStep = usDone then
    Log('Nodra uninstall cleanup completed');
end;
