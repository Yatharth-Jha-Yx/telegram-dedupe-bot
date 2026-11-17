# Prints the bot's webhook status and group permissions (token never shown).
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$secure = Read-Host "Paste your bot token (input hidden)" -AsSecureString
$token = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
  [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))

$me = (Invoke-RestMethod "https://api.telegram.org/bot$token/getMe").result
"Bot: @$($me.username)  reads all group messages (privacy off): $($me.can_read_all_group_messages)"

$w = (Invoke-RestMethod "https://api.telegram.org/bot$token/getWebhookInfo").result
"Webhook URL:     $($w.url)"
"Pending updates: $($w.pending_update_count)"
"Allowed updates: $($w.allowed_updates -join ', ')"
if ($w.last_error_date) {
  "Last error:      $($w.last_error_message) at $([DateTimeOffset]::FromUnixTimeSeconds($w.last_error_date).LocalDateTime)"
} else { "Last error:      none" }
