# Creates a desktop shortcut "UTi260B Thermal Studio" with the thermometer icon.
$root = Split-Path -Parent $PSScriptRoot
$pyw = (Get-Command pythonw -ErrorAction Stop).Source
$lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) 'UTi260B Thermal Studio.lnk'
$sh = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$sh.TargetPath = $pyw
$sh.Arguments = '-m uti260b'
$sh.WorkingDirectory = $root
$sh.IconLocation = (Join-Path $root 'uti260b\gui\thermometer.ico')
$sh.Save()
"Created $lnk"
