@echo off
title Houdini AI Server
cd /d "%~dp0"

echo ========================================
echo   Houdini AI Server
echo ========================================
echo.
echo Starting...
echo   Web UI:  http://127.0.0.1:9000
echo   MCP:     http://127.0.0.1:9000/mcp
echo.
echo Make sure Houdini Bridge is running in Houdini!
echo (Shelf Tool: bridge/shelf_tool.py)
echo.

python -m mcp_server.main

pause
