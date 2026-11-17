# Stores your bot token + a random webhook secret on the Worker,
# then points Telegram at the Worker. Nothing sensitive is written to disk.
#
# Usage (from the project folder, after `npx wrangler deploy`):
#   powershell -ExecutionPolicy Bypass -File .\scripts\connect-telegram.ps1 -WorkerUrl https://<name>.<subdomain>.workers.dev
param([Parameter(Mandatory = $true)][string]$WorkerUrl)

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$npx = if ($IsWindows -or $env:OS -eq "Windows_NT") { "npx.cmd" } else { "npx" }

$secure = Read-Host "Paste your bot token (input hidden)" -AsSecureString
$token = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
  [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)).Trim()

$secret = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 40 | ForEach-Object { [char]$_ })

$token  | & $npx wrangler secret put BOT_TOKEN
$secret | & $npx wrangler secret put WEBHOOK_SECRET

$body = @{
  url                  = $WorkerUrl
  secret_token         = $secret
  allowed_updates      = @("message", "channel_post")
  drop_pending_updates = $true
} | ConvertTo-Json
$r = Invoke-RestMethod -Method Post -ContentType "application/json" `
  -Uri "https://api.telegram.org/bot$token/setWebhook" -Body $body
"setWebhook: ok=$($r.ok) $($r.description)"
