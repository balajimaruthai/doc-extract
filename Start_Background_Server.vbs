Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
strPath = FSO.GetParentFolderName(WScript.ScriptFullName)
pythonwPath = "C:\Users\Zynee\anaconda3\pythonw.exe"
If Not FSO.FileExists(pythonwPath) Then
    pythonwPath = "pythonw.exe"
End If
WshShell.CurrentDirectory = strPath
WshShell.Environment("PROCESS")("DOCEXTRACT_DEMO") = "1"
WshShell.Environment("PROCESS")("DOCEXTRACT_HOST") = "0.0.0.0"
WshShell.Run """" & pythonwPath & """ -m uvicorn main:app --app-dir """ & strPath & "\app\backend"" --host 0.0.0.0 --port 37240", 0, False
