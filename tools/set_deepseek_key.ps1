# 把你的 DeepSeek API 密钥保存到这台电脑的用户环境变量 DEEPSEEK_API_KEY 里。
# 输入时屏幕上不显示，也不会被打印出来；只保存在你的电脑上。
# 用途：测试“Claude Code + DeepSeek 模型”能不能把请求送到手机上。

Write-Host ""
Write-Host "请粘贴你的 DeepSeek API 密钥（以 sk- 开头），然后按回车。输入时屏幕上不会显示："
$secure = Read-Host -AsSecureString
$plain = [System.Net.NetworkCredential]::new("", $secure).Password.Trim()
if (-not $plain.StartsWith("sk-")) {
    Write-Host "看起来不像 DeepSeek 密钥（应以 sk- 开头），没有保存。" -ForegroundColor Red
    exit 1
}
[System.Environment]::SetEnvironmentVariable("DEEPSEEK_API_KEY", $plain, "User")
Write-Host "已保存。现在可以回到对话里告诉 Claude：密钥设好了。" -ForegroundColor Green
