@echo off
setlocal
cd /d "%~dp0"

echo.
echo Este atalho apenas chama o instalador+runner.
echo Se preferir, rode direto: 1clique_instalar_e_rodar.bat
echo.

call "%~dp0\1clique_instalar_e_rodar.bat"
