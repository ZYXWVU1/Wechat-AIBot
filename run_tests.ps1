$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m unittest discover -s tests -v
python -m compileall -q windows_bridge nas_backend tests

