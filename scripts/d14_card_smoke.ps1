# D14 REAL WRITE smoke. Run ONLY on backed-up isolated TEST DATABASE!
# Set $env:D14_BANK_BEARER = 'Bearer ...' in the SAME terminal; never print or commit it.
param([string]$Base = 'http://127.0.0.1:8080')
$ErrorActionPreference='Stop'
if (-not $env:D14_BANK_BEARER -or -not $env:D14_BANK_BEARER.StartsWith('Bearer ')) {
    throw 'Missing D14_BANK_BEARER: acquire with /api/auth/login in a dedicated test account.'
}
$h=@{ Authorization=$env:D14_BANK_BEARER }
function ReadApi([string]$path) {
    Invoke-RestMethod -Uri "$Base$path" -Headers $h -Method Get
}
function WriteApi([string]$path, [hashtable]$body) {
    $json=$body|ConvertTo-Json -Compress
    Invoke-RestMethod -Uri "$Base$path" -Headers $h -ContentType 'application/json' -Method Post -Body ([Text.Encoding]::UTF8.GetBytes($json))
}
function Assert([bool]$ok,[string]$message) {if(-not $ok){throw "D14 smoke FAIL: $message"}}
try {
    # Read-only first. This smoke intentionally issues one simulated alias per demo account.
    $before=ReadApi '/api/demo/balance'
    $existing=ReadApi '/api/demo/cards'
    if($null -ne $existing -and @($existing).Count -gt 0) {
        Write-Host 'This demo user already has a card. Use a fresh dedicated account; NO new card was created.' -ForegroundColor Yellow
        return
    }
    $rid='d14-card-'+[guid]::NewGuid().ToString('N')
    $app=WriteApi '/api/demo/cards/applications/prepare' @{cardType='VIRTUAL_DEBIT';requestId=$rid}
    Assert ($app.status -eq 'PENDING_APPROVAL') 'application is not pending'
    $same=WriteApi '/api/demo/cards/applications/prepare' @{cardType='VIRTUAL_DEBIT';requestId=$rid}
    Assert ($same.applicationId -eq $app.applicationId) 'repeat prepare created another application'
        $notYet=ReadApi '/api/demo/cards'
    Assert ($null -eq $notYet -or @($notYet).Count -eq 0) 'card issued before user confirmation'
    Assert ([decimal](ReadApi '/api/demo/balance').balance -eq [decimal]$before.balance) 'balance changed during preparation'

    $issued=WriteApi "/api/demo/cards/applications/$($app.applicationId)/confirm" @{confirmed=$true}
    Assert ($issued.status -eq 'ISSUED') 'Java did not confirm issuance'
    $again=WriteApi "/api/demo/cards/applications/$($app.applicationId)/confirm" @{confirmed=$true}
    Assert ($again.status -eq 'ISSUED') 'duplicate confirm incorrect'
    $cards=ReadApi '/api/demo/cards'
    Assert (@($cards).Count -eq 1) 'not exactly one card'
    $card=@($cards)[0]
    Assert ($card.cardAlias.StartsWith('BP-VC-')) 'card alias is not demo-only'
    Assert ([decimal](ReadApi '/api/demo/balance').balance -eq [decimal]$before.balance) 'issuing card changed balance'

    $req='d14-narrow-'+[guid]::NewGuid().ToString('N')
    $restriction=@{singleTransactionLimit='250.00';disableOnline=$true;requestId=$req}
    $limited=WriteApi "/api/demo/cards/$($card.cardId)/restrictions" $restriction
    Assert ([decimal]$limited.singleTransactionLimit -eq [decimal]250) 'limit did not decrease'
    Assert (-not $limited.onlineEnabled) 'online flag remains enabled'
    $repeat=WriteApi "/api/demo/cards/$($card.cardId)/restrictions" $restriction
    Assert ([decimal]$repeat.singleTransactionLimit -eq [decimal]250) 'duplicate restriction altered state'
    Write-Host "D14 TEST PASS: application=$($app.applicationId), cardId=$($card.cardId), alias=$($card.cardAlias)" -ForegroundColor Green
    Write-Host 'Verified prepare, idempotent issue, no balance mutation, narrower limit, repeated restriction.'
} finally {
    Remove-Item Env:D14_BANK_BEARER -ErrorAction SilentlyContinue
}
