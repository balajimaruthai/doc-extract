Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
strPath = FSO.GetParentFolderName(WScript.ScriptFullName)
pythonwPath = "C:\Users\Zynee\anaconda3\pythonw.exe"
If Not FSO.FileExists(pythonwPath) Then
    pythonwPath = "pythonw.exe"
End If
WshShell.CurrentDirectory = strPath
WshShell.Run """" & pythonwPath & """ """ & strPath & "\app_desktop.pyw""", 0, False

