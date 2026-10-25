@echo off
rem Clone k0ngsmash/candle (fork of john-sharratt/candle) to D:, build the CUDA test binary,
rem then run the smallest gate (Qwen2-0.5B) as a smoke test. Logs go to D:\candle-work\logs.
setlocal
set WORK=D:\candle-work
set REPO=%WORK%\candle
set LOGS=%WORK%\logs
if not exist "%LOGS%" mkdir "%LOGS%"
set STATUS=%LOGS%\status.txt
echo started %DATE% %TIME% > "%STATUS%"

rem --- environment (set explicitly so this works even if Explorer has stale env) ---
set "CUDA_PATH=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.9"
set CUDARC_CUDA_VERSION=12090
set HF_HOME=%WORK%\hf-cache
set RUSTUP_HOME=D:\rust\rustup
set CARGO_HOME=D:\rust\cargo
call "D:\VS\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
set "PATH=%CUDA_PATH%\bin;D:\rust\cargo\bin;C:\Program Files\Git\cmd;%PATH%"

rem --- clone (partial clone: full history, file contents fetched on demand) ---
if not exist "%REPO%\.git" (
  echo [1/3] Cloning...
  git clone --filter=blob:none https://github.com/k0ngsmash/candle.git "%REPO%" > "%LOGS%\clone.log" 2>&1
  if errorlevel 1 ( echo CLONE FAILED >> "%STATUS%" & goto :end )
  git -C "%REPO%" config core.longpaths true
  git -C "%REPO%" remote add upstream https://github.com/john-sharratt/candle.git
)
git -C "%REPO%" fetch upstream >> "%LOGS%\clone.log" 2>&1
git -C "%REPO%" checkout main >> "%LOGS%\clone.log" 2>&1
git -C "%REPO%" merge --ff-only upstream/main >> "%LOGS%\clone.log" 2>&1
for /f %%c in ('git -C "%REPO%" rev-parse --short HEAD') do set COMMIT=%%c
echo commit %COMMIT% >> "%STATUS%"

cd /d "%REPO%"

rem --- build the candle-transformers test binary with CUDA (first time compiles 720+ kernels) ---
echo [2/3] Building (first build is long - tens of minutes)...
echo build start %TIME% >> "%STATUS%"
cargo test --release --features cuda -p candle-transformers --lib --no-run > "%LOGS%\build.log" 2>&1
set BUILD_EXIT=%ERRORLEVEL%
echo build exit %BUILD_EXIT% at %TIME% >> "%STATUS%"
if not "%BUILD_EXIT%"=="0" goto :end

rem --- smoke gate: Qwen2-0.5B (downloads ~350 MB of weights on first run) ---
echo [3/3] Running Qwen2-0.5B gate...
nvidia-smi --query-gpu=memory.used,memory.total --format=csv > "%LOGS%\vram_before_qwen2.txt"
cargo test --release --features cuda -p candle-transformers --lib models::quantized_qwen2::tests::test_parallel_batched_forwarding -- --exact --ignored --nocapture --test-threads=1 > "%LOGS%\gate_qwen2_%COMMIT%.log" 2>&1
echo gate qwen2 exit %ERRORLEVEL% at %TIME% >> "%STATUS%"

:end
echo finished %DATE% %TIME% >> "%STATUS%"
type "%STATUS%"
echo.
echo Done - tell Claude.
pause
