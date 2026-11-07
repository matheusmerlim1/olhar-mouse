# Libera no firewall do Windows as portas da camera do celular do olhar-mouse
# (8443-8452, TCP, somente rede PRIVADA). Precisa de administrador: o Windows
# pede confirmacao. Uso: botao direito no arquivo > "Executar com o PowerShell".
# Para desfazer: Remove-NetFirewallRule -DisplayName "Olhar-mouse (camera do celular)"
$nome = "Olhar-mouse (camera do celular)"
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}
Get-NetFirewallRule -DisplayName $nome -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $nome -Direction Inbound -Protocol TCP -LocalPort 8443-8452 `
    -Profile Private -Action Allow | Out-Null
Write-Host "Regra criada: $nome (TCP 8443-8452, somente rede privada)."
Start-Sleep -Seconds 3
