Option Explicit
Dim shell, files, root, pythonw, command, logFile
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
root = files.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = root
pythonw = files.BuildPath(root, ".venv\Scripts\pythonw.exe")
If Not files.FileExists(pythonw) Then pythonw = "pythonw.exe"
command = Chr(34) & pythonw & Chr(34) & " " & Chr(34) & files.BuildPath(root, "launch.pyw") & Chr(34)
On Error Resume Next
shell.Run command, 0, False
If Err.Number <> 0 Then
    If Not files.FolderExists(files.BuildPath(root, "runtime")) Then files.CreateFolder files.BuildPath(root, "runtime")
    Set logFile = files.OpenTextFile(files.BuildPath(root, "runtime\launcher_error.log"), 8, True)
    logFile.WriteLine "Cannot start pythonw. Run setup.ps1 first."
    logFile.Close
End If
