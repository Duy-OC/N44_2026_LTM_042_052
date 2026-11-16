@echo off
setlocal enabledelayedexpansion

echo ======================================================
echo    PBL3 MAVLink Gateway - One-Command Build Script
echo ======================================================

if not exist bin mkdir bin
set CXX=g++
set CXXFLAGS=-std=c++17 -O2 -Isrc/common -Isrc/gateway -Isrc/proxy -Isrc/client -Ithird_party
set LDFLAGS=-lws2_32

echo [1/3] Compiling Gateway (src/gateway/gateway.cpp)...
%CXX% %CXXFLAGS% -o bin\gateway.exe src\gateway\gateway.cpp %LDFLAGS%
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Gateway build failed!
    exit /b 1
)

echo [2/3] Compiling TCP Client (src/client/tcpclient.cpp)...
%CXX% %CXXFLAGS% -o bin\tcpclient.exe src/client/tcpclient.cpp %LDFLAGS%
if %ERRORLEVEL% neq 0 (
    echo [ERROR] TCP Client build failed!
    exit /b 1
)

echo [3/3] Compiling Markov Proxy (src/proxy/upstream_markov_proxy.cpp)...
%CXX% %CXXFLAGS% -o bin\upstream_markov_proxy.exe src/proxy/upstream_markov_proxy.cpp %LDFLAGS%
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Markov Proxy build failed!
    exit /b 1
)

echo.
echo ======================================================
echo [SUCCESS] Build hoan tat! Cac file thuc thi:
echo   - bin\gateway.exe
echo   - bin\tcpclient.exe
echo   - bin\upstream_markov_proxy.exe
echo ======================================================
