# D13 authenticated simulated-investment smoke test. Real writes to TEST database.
# Use a freshly backed up isolated DB. Do NOT run on production or on main demo DB.
param([string]$Base = 'http://127.0.0.1:8080', [long]$ProductId = 101)
$ErrorActionPreference = 'Stop'
if (-not $env:D13_BANK_BEARER -or -not $env:D13_BANK_BEARER.StartsWith('Bearer ')) {
    throw 'Set D13_BANK_BEARER to a VALID demo-user bearer in this terminal (do not print it).'
}
$headers = @{ Authorization = $env:D13_BANK_BEARER }
function Get-Bank([string]$path) { Invoke-RestMethod -Uri "$Base$path" -Headers $headers -Method Get }
function Post-Bank([string]$path, [hashtable]$body) {
    $j = $body | ConvertTo-Json -Compress
    Invoke-RestMethod -Uri "$Base$path" -Headers $headers -Method Post -ContentType 'application/json' -Body ([Text.Encoding]::UTF8.GetBytes($j))
}
function Check([bool]$v,[string]$reason) { if(-not $v) { throw "D13 smoke FAIL: $reason" } }
try {
    $products = @(Get-Bank '/api/demo/investments/products')
    $p = $products | Where-Object { $_.productId -eq $ProductId } | Select-Object -First 1
    Check ($null -ne $p) 'product missing'
    # Demo-only questionnaire. R1 purchase always fits R1 suitability.
    $profile = Post-Bank '/api/demo/investments/profile/assess' @{lossTolerance=1;horizon=1;experience=1}
    Check ($profile.riskLevel -eq 1) 'profile assessment failed'
    $before = [decimal](Get-Bank '/api/demo/balance').balance
    $nav=[decimal]$p.nav
    Check ($before -ge ($nav*2)) 'demo account needs enough funds'
    $posBefore = @(Get-Bank '/api/demo/investments/portfolio') | Where-Object { $_.productId -eq $ProductId } | Select-Object -First 1
    $qtyBefore = if($posBefore) {[decimal]$posBefore.units} else {[decimal]0}

    $rid='d13-smoke-'+[guid]::NewGuid().ToString('N')
    $prepared=Post-Bank '/api/demo/investments/orders/prepare' @{productId=$ProductId;action='BUY';units='2';requestId=$rid}
    Check ($prepared.status -eq 'PENDING_APPROVAL') 'buy not awaiting approval'
    Check ([decimal](Get-Bank '/api/demo/balance').balance -eq $before) 'prepare debited cash'
    $approved=Post-Bank "/api/demo/investments/orders/$($prepared.orderId)/confirm" @{confirmed=$true}
    Check ($approved.status -eq 'SUCCESS') 'buy not successful'
    $again=Post-Bank "/api/demo/investments/orders/$($prepared.orderId)/confirm" @{confirmed=$true}
    Check ($again.status -eq 'SUCCESS') 'idempotent confirm failed'
    Check ([decimal](Get-Bank '/api/demo/balance').balance -eq ($before - ($nav*2))) 'buy cash delta incorrect'
    $pAfter=@(Get-Bank '/api/demo/investments/portfolio') | Where-Object { $_.productId -eq $ProductId } | Select-Object -First 1
    Check ([decimal]$pAfter.units -eq ($qtyBefore+2)) 'holding after buy incorrect'

    $redId='d13-redeem-'+[guid]::NewGuid().ToString('N')
    $red=Post-Bank '/api/demo/investments/orders/prepare' @{productId=$ProductId;action='REDEEM';units='1';requestId=$redId}
    Check ([decimal](Get-Bank '/api/demo/balance').balance -eq ($before-($nav*2))) 'redeem prepare moved funds'
    $sold=Post-Bank "/api/demo/investments/orders/$($red.orderId)/confirm" @{confirmed=$true}
    Check ($sold.status -eq 'SUCCESS') 'redeem not successful'
    Check ([decimal](Get-Bank '/api/demo/balance').balance -eq ($before-$nav)) 'redeem cash delta incorrect'
    $pFinal=@(Get-Bank '/api/demo/investments/portfolio') | Where-Object { $_.productId -eq $ProductId } | Select-Object -First 1
    Check ([decimal]$pFinal.units -eq ($qtyBefore+1)) 'final holding incorrect'
    Write-Host 'D13 REAL JAVA/MYSQL BUY + IDEMPOTENCY + REDEEM: PASS' -ForegroundColor Green
    Write-Host "Bank order IDs: BUY=$($prepared.orderId), REDEEM=$($red.orderId) (no credentials displayed)"
} finally {
    Remove-Item Env:D13_BANK_BEARER -ErrorAction SilentlyContinue
}
