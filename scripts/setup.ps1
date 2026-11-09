# One-time setup for Magpie Voice. Safe to run again: finished steps are skipped.
#   pwsh -File scripts\setup.ps1
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Version = '0.3.0'
$ZipName = "nemo-speech-$Version-windows-x86_64-cpu.zip"
$ZipUrl  = "https://github.com/NVIDIA/NeMo-Speech.cpp/releases/download/v$Version/$ZipName"
$ZipSha  = '4ed9740e361e4653f56c3dce7d1e81883a1c8b831c1bd7d01567fff1130b5b05'
$EngineDir = Join-Path $Root "vendor\nemo-speech"
$Exe = Join-Path $EngineDir "nemo-speech-$Version-windows-x86_64-cpu\bin\nemo-speech.exe"
$Models = Join-Path $Root 'models'
$summary = [ordered]@{}

function Step($name, [scriptblock]$done, [scriptblock]$do) {
    if (& $done) { $summary[$name] = 'already done'; Write-Host "[skip] $name"; return }
    Write-Host "[....] $name"
    & $do
    $summary[$name] = 'done'
}

Step 'Speech engine (NeMo-Speech.cpp CPU)' { Test-Path $Exe } {
    $dl = Join-Path $Root 'vendor\dl'
    New-Item -ItemType Directory -Force $dl | Out-Null
    $zip = Join-Path $dl $ZipName
    Invoke-WebRequest $ZipUrl -OutFile $zip
    $hash = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
    if ($hash -ne $ZipSha) { Remove-Item $zip; throw "Checksum mismatch for $ZipName ($hash)" }
    Expand-Archive $zip -DestinationPath $EngineDir -Force
}

Step 'Magpie model (about 650 MB)' {
    Test-Path (Join-Path $Models 'nvidia\magpie_tts_multilingual_357m')
} {
    $env:NEMO_SPEECH_MODEL_DIR = $Models
    & $Exe pull magpie
    if ($LASTEXITCODE -ne 0) { throw 'Model download failed' }
}

Step 'Python environment (uv sync)' { Test-Path (Join-Path $Root '.venv\Scripts\magpie-voice.exe') } {
    uv sync
    if ($LASTEXITCODE -ne 0) { throw 'uv sync failed' }
}

Step 'Register MCP server with Claude Code (user scope)' {
    claude mcp get magpie-voice *> $null; $LASTEXITCODE -eq 0
} {
    # '--' must be quoted: PowerShell otherwise consumes it and claude sees uv's flags.
    claude mcp add --scope user magpie-voice '--' uv run --directory "$Root" magpie-voice mcp
    if ($LASTEXITCODE -ne 0) { throw 'claude mcp add failed' }
}

$SkillSrc = Join-Path $Root 'skill\magpie-voice\SKILL.md'
$SkillDst = Join-Path $HOME '.claude\skills\magpie-voice\SKILL.md'
Step 'Install Claude skill' {
    (Test-Path $SkillDst) -and ((Get-FileHash $SkillDst).Hash -eq (Get-FileHash $SkillSrc).Hash)
} {
    New-Item -ItemType Directory -Force (Split-Path $SkillDst) | Out-Null
    Copy-Item $SkillSrc $SkillDst -Force
}

$Lnk = Join-Path ([Environment]::GetFolderPath('Programs')) 'Magpie Voice.lnk'
Step 'Start-menu shortcut' { Test-Path $Lnk } {
    $sh = (New-Object -ComObject WScript.Shell).CreateShortcut($Lnk)
    $sh.TargetPath = Join-Path $Root '.venv\Scripts\pythonw.exe'
    $sh.Arguments = '-m magpie_voice gui'
    $sh.WorkingDirectory = $Root
    $sh.Description = 'Magpie Voice text-to-speech'
    $sh.Save()
}

Write-Host ''
Write-Host 'Magpie Voice setup summary'
$summary.GetEnumerator() | ForEach-Object { Write-Host ("  {0,-50} {1}" -f $_.Key, $_.Value) }
Write-Host ''
Write-Host 'Try:  uv run magpie-voice say "Hello from Magpie Voice"'
Write-Host 'Open a NEW Claude Code session to pick up the MCP server and skill.'
