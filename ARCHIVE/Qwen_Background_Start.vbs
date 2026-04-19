Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = scriptDir

pythonPath = "C:\Users\user\AppData\Local\Programs\Python\Python310\pythonw.exe"
scriptPath = "qwen_unified_live.py"
cmd = """" & pythonPath & """ """ & scriptPath & """ --mode live --interval 60"

' Only start if not already running
Dim alreadyRunning
alreadyRunning = False
On Error Resume Next
Set colProcesses = GetObject("winmgmts:{impersonationLevel=impersonate}!\\.\root\cimv2").ExecQuery("Select * from Win32_Process Where Name='pythonw.exe'")
If colProcesses.Count > 0 Then
    alreadyRunning = True
End If
On Error GoTo 0

If Not alreadyRunning Then
    Do
        WshShell.Run cmd, 0, True
        WScript.Sleep 10000
    Loop
End If
