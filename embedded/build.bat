@echo off
mkdir build 2>nul
echo Building Core Files...
set CORE_FILES=src\dwt.cpp src\dwt_fixed.cpp src\guardrail.cpp src\escrow.cpp src\uncertainty.cpp src\resource_controller.cpp src\telemetry.cpp src\pipeline.cpp

echo Building eventvault_app.exe...
g++ -std=c++17 -Wall -Wextra -static -Iinclude %CORE_FILES% app\main.cpp -o build\eventvault_app.exe

echo Building fixed_point_eval.exe...
g++ -std=c++17 -Wall -Wextra -static -Iinclude %CORE_FILES% app\fixed_point_eval.cpp -o build\fixed_point_eval.exe

echo Building test_dwt.exe...
g++ -std=c++17 -Wall -Wextra -static -Iinclude %CORE_FILES% tests\test_dwt.cpp -o build\test_dwt.exe

echo.
echo Build Successful! Check the 'build' folder.
pause
