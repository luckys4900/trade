Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "pythonw.exe qwen_unified_live.py --mode live --interval 60", 0, False
