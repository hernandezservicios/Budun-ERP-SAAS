$ErrorActionPreference = 'SilentlyContinue'
Write-Host '=== ERP SaaS Environment Check ==='
$checks = @(
  @{Name='Python'; Cmd='python --version'},
  @{Name='Git'; Cmd='git --version'},
  @{Name='Node'; Cmd='node --version'},
  @{Name='npm'; Cmd='npm --version'},
  @{Name='PostgreSQL client'; Cmd='psql --version'}
)
foreach ($c in $checks) {
  Write-Host "`n[$($c.Name)]"
  try { Invoke-Expression $c.Cmd } catch { Write-Host 'NOT FOUND' }
}
Write-Host "`nPostgreSQL Windows services:"
Get-Service *postgres* | Select-Object Name, Status, StartType
Write-Host "`nNOTE: Docker is intentionally NOT required for this project."
