# Dot-sourced by run.ps1 / diag.ps1. OPT-IN display refresh switch.
#
# The 60 fps engine mod presents 59.94 frames per second. The intended setup
# is G-SYNC/FreeSync with the game fullscreen (config/settings.toml): the panel
# then follows the runtime's precise frame pacer. This helper is for panels
# WITHOUT variable refresh: set  $env:DISRUPTOR_REFRESH_HZ = '120'  (or '60')
# and run.ps1 switches the primary display to that rate while the game runs.
# It is not the default because on the NVIDIA + compositor setup it was
# measured on, driver vsync does not block the swap, so a fixed 120/60 Hz mode
# paced less evenly than "immediate" presents.
#
# The change uses CDS_FULLSCREEN, i.e. it is temporary: Windows restores the
# desktop mode by itself when this PowerShell process exits, even if the
# script is killed. Exit-GameRefresh restores it explicitly.
if (-not ('Disruptor.DisplayMode' -as [type])) {
    Add-Type -Namespace Disruptor -Name DisplayMode -MemberDefinition @'
[StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
public struct DEVMODE {
    [MarshalAs(UnmanagedType.ByValArray, SizeConst = 32)] public ushort[] dmDeviceName;
    public ushort dmSpecVersion, dmDriverVersion, dmSize, dmDriverExtra;
    public uint dmFields;
    public int dmPositionX, dmPositionY;
    public uint dmDisplayOrientation, dmDisplayFixedOutput;
    public short dmColor, dmDuplex, dmYResolution, dmTTOption, dmCollate;
    [MarshalAs(UnmanagedType.ByValArray, SizeConst = 32)] public ushort[] dmFormName;
    public ushort dmLogPixels;
    public uint dmBitsPerPel, dmPelsWidth, dmPelsHeight, dmDisplayFlags, dmDisplayFrequency;
    public uint dmICMMethod, dmICMIntent, dmMediaType, dmDitherType, dmReserved1, dmReserved2, dmPanningWidth, dmPanningHeight;
}
[DllImport("user32.dll", CharSet = CharSet.Unicode)]
public static extern bool EnumDisplaySettingsW(IntPtr device, int modeNum, ref DEVMODE mode);
[DllImport("user32.dll", CharSet = CharSet.Unicode)]
public static extern int ChangeDisplaySettingsW(ref DEVMODE mode, uint flags);
[DllImport("user32.dll", CharSet = CharSet.Unicode, EntryPoint = "ChangeDisplaySettingsW")]
public static extern int RestoreDisplaySettings(IntPtr mode, uint flags);
public static DEVMODE NewMode() {
    DEVMODE m = new DEVMODE();
    m.dmDeviceName = new ushort[32];
    m.dmFormName = new ushort[32];
    m.dmSize = (ushort)Marshal.SizeOf(typeof(DEVMODE));
    return m;
}
'@
}

function Enter-GameRefresh {
    if (-not $env:DISRUPTOR_REFRESH_HZ) { return $false }
    $cur = [Disruptor.DisplayMode]::NewMode()
    if (-not [Disruptor.DisplayMode]::EnumDisplaySettingsW([IntPtr]::Zero, -1, [ref]$cur)) { return $false }
    $hz = [int]$cur.dmDisplayFrequency
    # Already a multiple of 59.94/60 within 1 %: nothing to do.
    $n = [math]::Round($hz / 60.0)
    if (-not $env:DISRUPTOR_REFRESH_HZ -and $n -ge 1 -and [math]::Abs($hz - $n * 60.0) -le 0.01 * $hz) { return $false }
    $best = 0
    $m = [Disruptor.DisplayMode]::NewMode()
    for ($i = 0; [Disruptor.DisplayMode]::EnumDisplaySettingsW([IntPtr]::Zero, $i, [ref]$m); $i++) {
        if ($m.dmPelsWidth -ne $cur.dmPelsWidth -or $m.dmPelsHeight -ne $cur.dmPelsHeight -or
            $m.dmBitsPerPel -ne $cur.dmBitsPerPel) { continue }
        $f = [int]$m.dmDisplayFrequency
        if ($f -le $hz -and $f -ge 60 -and ($f % 60) -eq 0 -and $f -gt $best) { $best = $f }
    }
    # Override: force a specific refresh rate, e.g. $env:DISRUPTOR_REFRESH_HZ = '60'.
    if ($env:DISRUPTOR_REFRESH_HZ) { $best = [int]$env:DISRUPTOR_REFRESH_HZ }
    if ($best -eq 0) {
        Write-Host "Display is $hz Hz and offers no 60 Hz multiple; 60 fps will not pace evenly." -ForegroundColor Yellow
        return $false
    }
    $cur.dmDisplayFrequency = [uint32]$best
    $cur.dmFields = 0x400000 -bor 0x80000 -bor 0x100000 -bor 0x40000   # FREQUENCY | WIDTH | HEIGHT | BPP
    $rc = [Disruptor.DisplayMode]::ChangeDisplaySettingsW([ref]$cur, 4)  # CDS_FULLSCREEN = temporary
    if ($rc -ne 0) {
        Write-Host "Could not switch the display to $best Hz (code $rc); staying at $hz Hz." -ForegroundColor Yellow
        return $false
    }
    Write-Host "Display: $hz Hz -> $best Hz while the game runs (each frame = $($best / 60) refreshes)."
    Start-Sleep -Milliseconds 1500   # let the panel settle before the game probes the refresh rate
    return $true
}

function Exit-GameRefresh {
    [void][Disruptor.DisplayMode]::RestoreDisplaySettings([IntPtr]::Zero, 0)
}
