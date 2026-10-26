# Creates (once) a self-signed code-signing certificate for the Nodra build and exports it
# to certs\nodra-codesign.pfx. Idempotent: reuses the existing cert in the user store.
# The PFX and its password stay under certs/ which is gitignored — never commit them.
param([string]$Subject = "CN=Nodra, O=Nodra Project, C=CN")

$ErrorActionPreference = "Stop"

$existing = Get-ChildItem Cert:\CurrentUser\My |
  Where-Object { $_.Subject -like "CN=Nodra*" -and $_.HasPrivateKey } |
  Sort-Object NotAfter -Descending | Select-Object -First 1

if ($existing) {
  Write-Host "reusing existing cert: $($existing.Subject) thumbprint=$($existing.Thumbprint) notAfter=$($existing.NotAfter)"
} else {
  $existing = New-SelfSignedCertificate `
    -Type CodeSigningCert `
    -Subject $Subject `
    -KeyUsage DigitalSignature -KeyExportPolicy Exportable -KeyLength 3072 `
    -HashAlgorithm SHA256 `
    -CertStoreLocation Cert:\CurrentUser\My `
    -NotAfter (Get-Date).AddYears(3) `
    -FriendlyName "Nodra Code Sign"
  Write-Host "created cert: $($existing.Subject) thumbprint=$($existing.Thumbprint)"
}

# Trust the (self-signed) root for this user so local Get-AuthenticodeSignature checks
# come out Valid; other machines still see an untrusted (but valid) signature.
$root = New-Object System.Security.Cryptography.X509Certificates.X509Store("Root", "CurrentUser")
$root.Open("ReadWrite")
if (-not ($root.Certificates | Where-Object { $_.Thumbprint -eq $existing.Thumbprint })) {
  $root.Add($existing)
}
$root.Close()

New-Item -ItemType Directory -Force -Path "$PSScriptRoot\..\certs" | Out-Null
$pfx = "$PSScriptRoot\..\certs\nodra-codesign.pfx"
$passFile = "$PSScriptRoot\..\certs\pfx-password.txt"
$bytes = New-Object byte[] 24
$rng = New-Object System.Security.Cryptography.RNGCryptoServiceProvider
$rng.GetBytes($bytes)
$password = [Convert]::ToBase64String($bytes)
[IO.File]::WriteAllText($passFile, $password)
Export-PfxCertificate -Cert $existing -FilePath $pfx -Password (ConvertTo-SecureString $password -AsPlainText -Force) | Out-Null
Write-Host "exported $pfx (password in certs\pfx-password.txt, both gitignored)"
