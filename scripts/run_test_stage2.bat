@echo off
setlocal enabledelayedexpansion

echo ===============================================================
echo     KICH BAN KIEM THU GIAI DOAN 2: GIAI MA TELEMETRY CHI TIET
echo ===============================================================

if not exist bin mkdir bin
if not exist docs\ketqua mkdir docs\ketqua

echo [1/2] Bien dich chuong trinh test tests/test_stage2_telemetry.cpp...
g++ -std=c++11 -O2 -Isrc/common -Isrc/gateway -Ithird_party -o bin\test_stage2_telemetry.exe tests\test_stage2_telemetry.cpp -lws2_32
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Bien dich test_stage2_telemetry that bai!
    exit /b 1
)

echo [2/2] Dang chay toan bo phep thu T2.1 - T2.6...
echo.
bin\test_stage2_telemetry.exe

echo.
echo ===============================================================
echo Kiem tra file ket qua tai: docs\ketqua\stage2_telemetry_results.csv
echo ===============================================================
