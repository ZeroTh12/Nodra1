# Authenticode-signs the given files with the Nodra code-signing certificate
# (created by make-codesign-cert.ps1) and RFC-3161 timestamps them.
# Self-signed: the signature is real and timestamped, but Windows does not trust the
# chain until the user installs the cert — AV reputation needs a CA-issued cert.
param(
  # One string; several files are separated by ';' or ',' (cmd-friendly).
  [Parameter(Mandatory = $true)][string]$Files,
  [string]$Pfx = "$PSScriptRoot\..\certs\nodra-codesign.pfx",
  [string]$PassFile = "$PSScriptRoot\..\certs\pfx-password.txt"
)
$ErrorActionPreference = "Stop"

$cert = Get-ChildItem Cert:\CurrentUser\My |
  Where-Object { $_.Subject -like "CN=Nodra*" -and $_.HasPrivateKey } |
  Sort-Object NotAfter -Descending | Select-Object -First 1

if (-not $cert) {
  if (-not (Test-Path $Pfx)) { throw "no cert in store and $Pfx missing; run make-codesign-cert.ps1 first" }
  $password = ConvertTo-SecureString ([IO.File]::ReadAllText($PassFile).Trim()) -AsPlainText -Force
  $cert = Import-PfxCertificate -FilePath $Pfx -CertStoreLocation Cert:\CurrentUser\My -Password $password
}

foreach ($file in ($Files -split '[;,]')) {
  $file = $file.Trim().Trim('"')
  if (-not $file) { continue }
  $result = Set-AuthenticodeSignature -FilePath $file -Certificate $cert `
    -IncludeChain All -HashAlgorithm SHA256 -TimeStampServer "http://timestamp.digicert.com"
  # A self-signed chain ends at an untrusted root: Windows reports UnknownError even
  # though the (timestamped) signature was applied. Only a missing signature is fatal.
  if (-not $result.SignerCertificate) {
    throw "signing failed for $file : $($result.StatusMessage)"
  }
  "{0}  signed by {1} (status {2}: {3})" -f (Split-Path $file -Leaf), $result.SignerCertificate.Subject, $result.Status, $result.StatusMessage | Write-Host
}
Write-Host "signed with: $($cert.Subject) (valid until $($cert.NotAfter.ToString('yyyy-MM-dd')))"
