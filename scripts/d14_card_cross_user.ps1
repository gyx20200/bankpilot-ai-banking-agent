# Read/approval/limit-modification boundary test using TWO distinct simulated-user tokens.
# Never print tokens. The unauthorized restriction call must not mutate card settings.
param(
    [string]$Base='http://127.0.0.1:8080',
    [Parameter(Mandatory=$true)][long]$ApplicationId,
    [Parameter(Mandatory=$true)][long]$CardId
)
$ErrorActionPreference='Stop'
if (-not $env:D14_TOKEN_A -or -not $env:D14_TOKEN_B) {throw 'Need D14_TOKEN_A and D14_TOKEN_B (Bearer-prefixed)'}
$ha=@{Authorization=$env:D14_TOKEN_A}
$hb=@{Authorization=$env:D14_TOKEN_B}
function Must-Deny([scriptblock]$block) {
    try { & $block | Out-Null }
    catch {
        $status = 0
        if ($_.Exception.Response) { $status=[int]$_.Exception.Response.StatusCode }
        if ($status -eq 403 -or $status -eq 404) {
            Write-Host "PASS: forbidden cross-user request -> HTTP $status" -ForegroundColor Green
            return
        }
        throw "Unexpected request failure: HTTP $status. $($_.Exception.GetType().Name)"
    }
    throw 'SECURITY FAILURE: cross-user request succeeded'
}
try {
    $mine=Invoke-RestMethod -Uri "$Base/api/demo/cards/applications/$ApplicationId" -Headers $ha
    if ($mine.applicationId -ne $ApplicationId) {throw 'User A could not read its own application'}
    Must-Deny {Invoke-RestMethod -Uri "$Base/api/demo/cards/applications/$ApplicationId" -Headers $hb}
    Must-Deny {Invoke-RestMethod -Uri "$Base/api/demo/cards/applications/$ApplicationId/confirm" -Headers $hb `
         -Method Post -ContentType 'application/json' -Body '{"confirmed":true}'}
    $payload=@{singleTransactionLimit='1.00';disableOnline=$true;requestId='d14-foreign-'+[guid]::NewGuid().ToString('N')} | ConvertTo-Json
    Must-Deny {Invoke-RestMethod -Uri "$Base/api/demo/cards/$CardId/restrictions" -Headers $hb `
         -Method Post -ContentType 'application/json' -Body $payload}
    Write-Host 'D14 CROSS-USER BOUNDARY: PASS' -ForegroundColor Green
} finally {
    Remove-Item Env:D14_TOKEN_A, Env:D14_TOKEN_B -ErrorAction SilentlyContinue
}
