#include "../dist/release-build/version.iss"
#define Stage "../dist/stage"

[Setup]
AppId={{8520B55B-9EBE-4777-BAD5-7B220D97677F}
AppName=Disruptor Recompiled
AppVersion={#AppVersion}
AppVerName=Disruptor Recompiled {#AppVersion}
AppPublisher=Disruptor Recompiled contributors
AppPublisherURL=https://github.com/Phroster/DisruptorRecomp
VersionInfoVersion={#WindowsVersion}
DefaultDirName={localappdata}\Programs\Disruptor Recompiled
DefaultGroupName=Disruptor Recompiled
DisableProgramGroupPage=yes
DisableWelcomePage=no
DisableDirPage=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.18362
WizardStyle=modern dynamic
WizardSizePercent=115
WizardImageFile=../dist/release-build/wizard.bmp
WizardSmallImageFile=../dist/release-build/wizard-small.bmp
SetupIconFile=../dist/release-build/disruptor.ico
UninstallDisplayIcon={app}\DisruptorLauncher.exe
UninstallDisplayName=Disruptor Recompiled
OutputDir=../dist
OutputBaseFilename=DisruptorRecompiled-{#AppVersion}-Setup
Compression=lzma2/max
SolidCompression=yes
CloseApplications=yes
CloseApplicationsFilter=DisruptorLauncher.exe,DisruptorRecompiled.exe,DisruptorBuilder.exe
RestartApplications=no
SetupLogging=yes
InfoBeforeFile=PLAYER-README.txt
LicenseFile=../dist/stage/docs/THIRD-PARTY-NOTICES.txt
; The build writes the game (about 25 MB) and uses about 350 MB of temporary files.
ExtraDiskSpaceRequired=400000000

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "{#Stage}\*"; DestDir: "{app}"; Excludes: ".release-owned,game\settings.toml,game\keybinds.ini,game\config.ini"; Flags: ignoreversion recursesubdirs createallsubdirs
; Player settings: installed once, kept on update and uninstall.
Source: "{#Stage}\game\settings.toml"; DestDir: "{app}\game"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "{#Stage}\game\keybinds.ini"; DestDir: "{app}\game"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "{#Stage}\game\config.ini"; DestDir: "{app}\game"; Flags: onlyifdoesntexist uninsneveruninstall
; This file is supplied by the player and is NEVER embedded in Setup.
Source: "{code:GetDiscSource}"; DestDir: "{app}\disc"; DestName: "Disruptor.bin"; ExternalSize: {#DiscSize}; Hash: "{#DiscHash}"; Flags: external ignoreversion; Check: CopyDiscNeeded

[InstallDelete]
; Anything an earlier version built or shipped prebuilt; the build below recreates it.
Type: filesandordirs; Name: "{app}\game\cache"
Type: filesandordirs; Name: "{app}\work"
Type: files; Name: "{app}\game\build-stamp.json"

[UninstallDelete]
; Everything the build and the game created on this PC. Saves live in the Windows
; profile, and settings files are kept.
Type: filesandordirs; Name: "{app}\work"
Type: filesandordirs; Name: "{app}\game\cache"
Type: filesandordirs; Name: "{app}\game\overlay_captures.json.d"
Type: files; Name: "{app}\game\DisruptorRecompiled.exe"
Type: files; Name: "{app}\game\build-stamp.json"
Type: files; Name: "{app}\game\overlay_captures.json"
Type: files; Name: "{app}\psx_last_run_report.json"

[Icons]
Name: "{group}\Disruptor Recompiled"; Filename: "{app}\DisruptorLauncher.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Disruptor Recompiled"; Filename: "{app}\DisruptorLauncher.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\DisruptorLauncher.exe"; Description: "Open Disruptor Recompiled"; Flags: nowait postinstall skipifsilent

[Code]
var
  DiscPage: TInputFileWizardPage;
  VerifyPage: TOutputProgressWizardPage;
  BuildPage: TOutputProgressWizardPage;
  DiscSource: String;
  DiscValidated: Boolean;
  BuildError: String;

function GetDiscSource(Param: String): String;
begin
  Result := DiscSource;
end;

function CopyDiscNeeded: Boolean;
begin
  Result := CompareText(ExpandFileName(DiscSource), ExpandFileName(ExpandConstant('{app}\disc\Disruptor.bin'))) <> 0;
end;

function CheckDisc: String;
var
  Size: Int64;
begin
  Result := '';
  DiscValidated := False;
  DiscSource := DiscPage.Values[0];
  if DiscSource = '' then DiscSource := ExpandConstant('{app}\disc\Disruptor.bin');
  if not FileExists(DiscSource) then begin
    Result := 'Pick your Disruptor USA disc image (.bin or .iso). A .cue file or a zip archive will not work.';
    exit;
  end;
  if not FileSize64(DiscSource, Size) then begin
    Result := 'Setup could not read this file. Check its location and try again.';
    exit;
  end;
  if Size <> {#DiscSize} then begin
    Result := 'This file is not the USA disc image of Disruptor. Pick the full .bin file (about 607 MB). Other versions, and compressed or converted images, will not work.';
    exit;
  end;
  VerifyPage.SetText('Verifying your disc image', 'Checking the complete file. This may take a few seconds.');
  VerifyPage.SetProgress(0, 1);
  VerifyPage.Show;
  try
    try
      if CompareText(GetSHA256OfFile(DiscSource), '{#DiscHash}') <> 0 then
        Result := 'This disc image is not the supported USA version of Disruptor, or it has been changed. Pick an unmodified copy of your disc.';
    except
      Result := 'Setup could not finish reading this image. Check that the file is accessible and try again.';
    end;
  finally
    VerifyPage.Hide;
  end;
  DiscValidated := Result = '';
end;

procedure InitializeWizard;
begin
  WizardForm.WelcomeLabel1.Caption := 'Disruptor. Recompiled for Windows.';
  WizardForm.WelcomeLabel2.Caption := 'Play Disruptor as a native Windows game. All you need is your own Disruptor USA disc image.' + #13#10#13#10 +
    'This download contains no game code or game data. Setup checks your disc image and builds the game from it on this PC. That takes about a minute, and nothing else is needed.' + #13#10#13#10 +
    'Your original image stays untouched. Saved games are kept in your Windows profile and survive uninstall.';
  DiscPage := CreateInputFilePage(wpSelectDir, 'Bring your disc', 'Select your Disruptor USA image (SLUS-00224).',
    'Pick your .bin or .iso disc image. Setup checks it, keeps a copy in the game folder and builds the game from it. If you have a .cue and a .bin, pick the .bin. Only the USA version of the game is supported.');
  DiscPage.Add('Disc image:', 'Disc images (*.bin;*.iso)|*.bin;*.iso|All files (*.*)|*.*', '.bin');
  DiscPage.Values[0] := ExpandConstant('{param:DISCFILE|}');
  VerifyPage := CreateOutputProgressPage('Verifying your disc', 'Preparing your installation.');
  BuildPage := CreateOutputProgressPage('Building Disruptor', 'Building the game from your disc on this PC. This takes about a minute.');
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = DiscPage.ID) and (DiscPage.Values[0] = '') and FileExists(ExpandConstant('{app}\disc\Disruptor.bin')) then
    DiscPage.Values[0] := ExpandConstant('{app}\disc\Disruptor.bin');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Error: String;
begin
  Result := True;
  if CurPageID = DiscPage.ID then begin
    Error := CheckDisc;
    Result := Error = '';
    if not Result then SuppressibleMsgBox(Error, mbError, MB_OK, IDOK);
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  { Also validate in unattended installs, which may skip wizard pages. }
  if DiscValidated and (DiscSource = DiscPage.Values[0]) then Result := ''
  else Result := CheckDisc;
end;

{ DisruptorBuilder prints "PROGRESS <percent> <text>" and "ERROR <text>" lines. }
procedure BuildOutput(const S: String; const Error, FirstLine: Boolean);
var
  Rest: String;
  Space: Integer;
begin
  Log('Build: ' + S);
  if Copy(S, 1, 9) = 'PROGRESS ' then begin
    Rest := Copy(S, 10, Length(S));
    Space := Pos(' ', Rest);
    if Space > 0 then begin
      BuildPage.SetText(Copy(Rest, Space + 1, Length(Rest)), 'The game is built from your disc on this PC. This takes about a minute.');
      BuildPage.SetProgress(StrToIntDef(Copy(Rest, 1, Space - 1), 0), 100);
    end;
  end else if Copy(S, 1, 6) = 'ERROR ' then
    BuildError := Copy(S, 7, Length(S));
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  Ok: Boolean;
begin
  if CurStep <> ssPostInstall then exit;
  BuildError := '';
  BuildPage.SetText('Preparing', '');
  BuildPage.SetProgress(0, 100);
  BuildPage.Show;
  try
    try
      Ok := ExecAndLogOutput(ExpandConstant('{app}\DisruptorBuilder.exe'), '', ExpandConstant('{app}'), SW_HIDE,
        ewWaitUntilTerminated, ResultCode, @BuildOutput) and (ResultCode = 0);
    except
      Ok := False;
      BuildError := GetExceptionMessage;
    end;
  finally
    BuildPage.Hide;
  end;
  if not Ok then begin
    if BuildError = '' then BuildError := 'The build tools stopped unexpectedly.';
    SuppressibleMsgBox('The game files are installed, but building the game did not finish:' + #13#10#13#10 + BuildError + #13#10#13#10 +
      'Open Disruptor Recompiled to try again. The build log is in %LOCALAPPDATA%\DisruptorRecompiled\logs.', mbError, MB_OK, IDOK);
  end;
end;
