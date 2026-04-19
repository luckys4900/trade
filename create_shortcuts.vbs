Set objShell = CreateObject("WScript.Shell")
strDesktop = objShell.SpecialFolders("Desktop")
strTradeDir = objShell.CurrentDirectory

' Create shortcut 1: Start System
Set objLink = objShell.CreateShortCut(strTradeDir & "\01_START.lnk")
objLink.TargetPath = "cmd.exe"
objLink.Arguments = "/k 01_Start_Whale_System.bat"
objLink.WorkingDirectory = strTradeDir
objLink.WindowStyle = 1
objLink.Save

' Create shortcut 2: Check Status
Set objLink = objShell.CreateShortCut(strTradeDir & "\03_STATUS.lnk")
objLink.TargetPath = "cmd.exe"
objLink.Arguments = "/k 03_Check_Status.bat"
objLink.WorkingDirectory = strTradeDir
objLink.WindowStyle = 1
objLink.Save

' Create shortcut 3: Stop System
Set objLink = objShell.CreateShortCut(strTradeDir & "\04_STOP.lnk")
objLink.TargetPath = "cmd.exe"
objLink.Arguments = "/k 04_Stop_System.bat"
objLink.WorkingDirectory = strTradeDir
objLink.WindowStyle = 1
objLink.Save

MsgBox "Shortcuts created successfully!", 64, "Done"
