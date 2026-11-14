@echo off
setlocal enabledelayedexpansion

echo ======================================================
echo    PBL3 MAVLink Gateway - One-Command Build Script
echo ======================================================

if not exist bin mkdir bin
if not exist logs mkdir logs
if not exist docs\ketqua mkdir docs\ketqua

set CXX=g++
set CXXFLAGS=-std=c++11 -O2 -Isrc/common -Isrc/gateway -Isrc/proxy -Isrc/client -Ithird_party
set LDFLAGS=-lws2_32

echo [1/4] Compiling Gateway (src/gateway/gateway.cpp)...
%CXX% %CXXFLAGS% -o bin\gateway.exe src\gateway\gateway.cpp %LDFLAGS%
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Gateway build failed!
    exit /b 1
)
copy /y bin\gateway.exe gateway.exe >nul

echo [2/4] Compiling TCP Client (src/client/tcpclient.cpp)...
%CXX% %CXXFLAGS% -o bin\tcpclient.exe src/client/tcpclient.cpp %LDFLAGS%
if %ERRORLEVEL% neq 0 (
    echo [ERROR] TCP Client build failed!
    exit /b 1
)
copy /y bin\tcpclient.exe tcpclient.exe >nul

echo [3/4] Compiling Markov Proxy (src/proxy/upstream_markov_proxy.cpp)...
%CXX% %CXXFLAGS% -o bin\upstream_markov_proxy.exe src/proxy/upstream_markov_proxy.cpp %LDFLAGS%
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Markov Proxy build failed!
    exit /b 1
)
copy /y bin\upstream_markov_proxy.exe upstream_markov_proxy.exe >nul

echo [4/4] Compiling Test T0.2 UDP Listener (tests/t0_2_udp_listener.cpp)...
%CXX% %CXXFLAGS% -o bin\t0_2_udp_listener.exe tests\t0_2_udp_listener.cpp %LDFLAGS%
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Test T0.2 build failed!
    exit /b 1
)
copy /y bin\t0_2_udp_listener.exe t0_2_udp_listener.exe >nul

echo.
echo ======================================================
echo [SUCCESS] Build hoan tat! Cac file thuc thi:
echo   - bin\gateway.exe (hoac .\gateway.exe)
echo   - bin\tcpclient.exe (hoac .\tcpclient.exe)
echo   - bin\upstream_markov_proxy.exe (hoac .\upstream_markov_proxy.exe)
echo   - bin\t0_2_udp_listener.exe (hoac .\t0_2_udp_listener.exe)
echo ======================================================
