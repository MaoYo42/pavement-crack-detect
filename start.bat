@echo off
echo =========================================
echo   启动路面裂缝辅助标注平台 (论文演示版)
echo =========================================

echo 正在激活虚拟环境并启动后台服务...
.\.venv\Scripts\uvicorn.exe app.main:app --reload --host 0.0.0.0 --port 8000

pause
