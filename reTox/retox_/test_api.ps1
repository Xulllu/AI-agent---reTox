# test_api.ps1 - PowerShell API Test Script

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "RETOX API TEST - PowerShell Version" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

$API_BASE = "http://localhost:5000"
$HEADERS = @{"Content-Type" = "application/json"}

function Test-Endpoint {
    param(
        [string]$Method,
        [string]$Endpoint,
        [object]$Body = $null,
        [int]$ExpectedStatus = 200
    )
    
    $Url = "$API_BASE$Endpoint"
    
    try {
        if ($Method -eq "GET") {
            $Response = Invoke-WebRequest -Uri $Url -Method Get -Headers $HEADERS -TimeoutSec 10
        } elseif ($Method -eq "POST") {
            $BodyJson = $Body | ConvertTo-Json -Depth 10
            $Response = Invoke-WebRequest -Uri $Url -Method Post -Headers $HEADERS -Body $BodyJson -TimeoutSec 10
        }
        
        if ($Response.StatusCode -eq $ExpectedStatus) {
            Write-Host "✓ $Method $Endpoint - Status $($Response.StatusCode)" -ForegroundColor Green
            return $Response.Content | ConvertFrom-Json
        } else {
            Write-Host "✗ $Method $Endpoint - Status $($Response.StatusCode)" -ForegroundColor Red
            return $null
        }
    }
    catch {
        Write-Host "✗ $Method $Endpoint - Error: $($_.Exception.Message)" -ForegroundColor Red
        return $null
    }
}

# Test 1: Health Check
Write-Host "[1/6] Testing Health Check..." -ForegroundColor Yellow
$health = Test-Endpoint -Method "GET" -Endpoint "/health"
if ($health) {
    Write-Host "  Status: $($health.status)`n" -ForegroundColor Green
}

# Test 2: Home Page
Write-Host "[2/6] Testing Home Page..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "$API_BASE/" -TimeoutSec 10
    if ($response.StatusCode -eq 200) {
        Write-Host "✓ GET / - Status 200`n" -ForegroundColor Green
    }
}
catch {
    Write-Host "✗ Home page error: $($_)" -ForegroundColor Red
}

# Test 3: Dashboard Page
Write-Host "[3/6] Testing Dashboard..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "$API_BASE/dashboard" -TimeoutSec 10
    if ($response.StatusCode -eq 200) {
        Write-Host "✓ GET /dashboard - Status 200`n" -ForegroundColor Green
    }
}
catch {
    Write-Host "✗ Dashboard error: $($_)" -ForegroundColor Red
}

# Test 4: Submit Comment
Write-Host "[4/6] Testing Comment Submission..." -ForegroundColor Yellow
$comment_body = @{
    external_id = "test_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    subreddit = "news"
    author = "testuser"
    text = "This is a test comment from PowerShell"
    reddit_score = 10
    reddit_permalink = "/r/news/comments/abc123"
}

$comment_response = Test-Endpoint -Method "POST" -Endpoint "/api/queue/submit" -Body $comment_body -ExpectedStatus 201
$comment_id = $null
if ($comment_response -and $comment_response.comment_id) {
    $comment_id = $comment_response.comment_id
    Write-Host "  Comment ID: $comment_id`n" -ForegroundColor Green
}

# Test 5: Submit Review
if ($comment_id) {
    Write-Host "[5/6] Testing Review Submission..." -ForegroundColor Yellow
    $review_body = @{
        comment_id = $comment_id
        decision = "approve"
        notes = "Test review from PowerShell"
    }
    
    $review_response = Test-Endpoint -Method "POST" -Endpoint "/api/reviews" -Body $review_body -ExpectedStatus 201
    if ($review_response) {
        Write-Host "  Review submitted successfully`n" -ForegroundColor Green
    }
}

# Test 6: Get Dashboard Stats
Write-Host "[6/6] Testing Dashboard Stats..." -ForegroundColor Yellow
$stats = Test-Endpoint -Method "GET" -Endpoint "/api/dashboard/stats"
if ($stats) {
    Write-Host "  Total comments: $($stats.summary.total_comments)" -ForegroundColor Green
    Write-Host "  Average toxicity: $($stats.summary.average_toxicity)" -ForegroundColor Green
    Write-Host "  Accuracy: $($stats.summary.accuracy_percent)%`n" -ForegroundColor Green
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "TESTS COMPLETE" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "You can now access:" -ForegroundColor Yellow
Write-Host "  🏠 Home:        http://localhost:5000" -ForegroundColor Cyan
Write-Host "  📊 Dashboard:   http://localhost:5000/dashboard" -ForegroundColor Cyan
Write-Host "  👥 Moderation:  http://localhost:5000/moderation" -ForegroundColor Cyan
Write-Host "  ⚙️  Admin:       http://localhost:5000/admin`n" -ForegroundColor Cyan