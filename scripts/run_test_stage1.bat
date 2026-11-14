@echo off
setlocal enabledelayedexpansion

echo ===============================================================
echo     KICH BAN KIEM THU GIAI DOAN 1: PARSE FRAME VA CRC MAVLINK
echo ===============================================================

if not exist bin mkdir bin
if not exist docs\ketqua mkdir docs\ketqua

echo [1/2] Bien dich chuong trinh test tests/test_stage1_framing.cpp...
g++ -std=c++11 -O2 -Isrc/common -Isrc/gateway -Ithird_party -o bin\test_stage1_framing.exe tests\test_stage1_framing.cpp -lws2_32
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Bien dich test_stage1_framing that bai!
    exit /b 1
)

echo [2/2] Dang chay toan bo phep thu T1.1 - T1.5...
echo.
bin\test_stage1_framing.exe

echo.
echo ===============================================================
echo Kiem tra file ket qua tai:
echo  1. CSV: docs\ketqua\stage1_framing_results.csv
echo  2. LOG: docs\ketqua\stage1_framing_log.txt
echo ===============================================================
