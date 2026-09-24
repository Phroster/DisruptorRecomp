# Dot-source in test launchers: my automated runs press buttons blindly and must
# never leave a mark on the player's memory card (a headless New Game did once).
#   . .\tools\card_guard.ps1;  $Guard = Save-CardState   ...   Restore-CardState $Guard
function Save-CardState {
    $Card = 'saves\card1.mcd'
    if (!(Test-Path $Card)) { return $null }
    New-Item -ItemType Directory -Force logs | Out-Null
    $Copy = 'logs\card1_guard_{0}.mcd' -f (Get-Date -Format yyyyMMdd_HHmmss_fff)
    Copy-Item $Card $Copy
    return @{ Card = $Card; Copy = $Copy; Hash = (Get-FileHash $Card).Hash }
}
function Restore-CardState($Guard) {
    if (!$Guard) { return }
    if ((Get-FileHash $Guard.Card).Hash -ne $Guard.Hash) {
        Copy-Item $Guard.Copy $Guard.Card -Force
        Write-Warning 'The test run changed saves\card1.mcd; restored it from the pre-run copy.'
    }
    Remove-Item $Guard.Copy -Confirm:$false -ErrorAction SilentlyContinue
}
