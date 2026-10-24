# 启动 CineLab 服务（含 ARK AI 解释）
# 用法: .\start-cinelab.ps1

$composeDir = $PSScriptRoot
$composeFiles = @(
    "$composeDir\compose.yaml",
    "$composeDir\docker-compose.dev.yml",
    "$composeDir\docker-compose.ark.yml"
)

# 检查 ark 文件是否存在
$arkFile = "$composeDir\docker-compose.ark.yml"
if (-not (Test-Path $arkFile)) {
    Write-Host "错误: 未找到 docker-compose.ark.yml" -ForegroundColor Red
    Write-Host "请创建该文件并配置 ARK_API_KEY 和 ARK_ENDPOINT" -ForegroundColor Yellow
    exit 1
}

# 构建命令参数
$args = @()
foreach ($f in $composeFiles) { $args += "-f"; $args += $f }
$args += "up"; $args += "-d"

Write-Host "启动 CineLab 服务..." -ForegroundColor Cyan
docker compose @args

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n服务已启动" -ForegroundColor Green
    Write-Host "  首页: http://127.0.0.1:8080/" -ForegroundColor White
    Write-Host "  电影库: http://127.0.0.1:8080/movies" -ForegroundColor White
    Write-Host "  推荐实验室: http://127.0.0.1:8080/experiments" -ForegroundColor White
} else {
    Write-Host "启动失败" -ForegroundColor Red
}
