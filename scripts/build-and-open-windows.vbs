Option Explicit
Dim shell, fso, folder, project, node, args, stateDir, logFile, checking
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
project = fso.GetParentFolderName(folder)
stateDir = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%")
If InStr(stateDir, "%") > 0 Or stateDir = "" Then stateDir = shell.ExpandEnvironmentStrings("%USERPROFILE%") & "\AppData\Local"
stateDir = stateDir & "\FLOWW\desktop-launcher"
EnsureFolder stateDir
logFile = stateDir & "\opening.log"
checking = False
If WScript.Arguments.Count > 0 Then checking = (WScript.Arguments(0) = "--check")
node = ResolveNode()
If node = "" Then
  LogEvent "NODE_NOT_FOUND: standard folders, saved install location and search path checked"
  If checking Then
    WScript.Echo "NODE_NOT_FOUND"
  Else
    MsgBox "FLOWW2 could not find Node. The opening log has the details.", 16, "FLOWW2"
  End If
  WScript.Quit 1
End If
LogEvent "NODE_READY: " & node
If checking Then
  WScript.Echo "NODE_READY"
  WScript.Quit 0
End If
args = Chr(34) & node & Chr(34) & " " & Chr(34) & folder & "\build-and-open-windows.cjs" & Chr(34)
shell.CurrentDirectory = project
On Error Resume Next
shell.Run args, 0, False
If Err.Number <> 0 Then
  LogEvent "OPEN_FAILED: " & CStr(Err.Number)
  MsgBox "FLOWW2 could not open. The opening log has the details.", 16, "FLOWW2"
  WScript.Quit 1
End If
On Error GoTo 0
LogEvent "OPEN_STARTED"

Sub EnsureFolder(p)
  If fso.FolderExists(p) Then Exit Sub
  EnsureFolder fso.GetParentFolderName(p)
  fso.CreateFolder p
End Sub

Sub LogEvent(message)
  Dim stream
  On Error Resume Next
  Set stream = fso.OpenTextFile(logFile, 8, True)
  stream.WriteLine CStr(Now) & " " & message
  stream.Close
  On Error GoTo 0
End Sub

Function ResolveNode()
  Dim candidates, candidate, install, entry
  candidates = Array(shell.ExpandEnvironmentStrings("%ProgramW6432%") & "\nodejs\node.exe", _
    "C:\Program Files\nodejs\node.exe", shell.ExpandEnvironmentStrings("%ProgramFiles%") & "\nodejs\node.exe", _
    shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\nodejs\node.exe")
  For Each candidate In candidates
    If fso.FileExists(candidate) Then ResolveNode = candidate : Exit Function
  Next
  On Error Resume Next
  install = shell.RegRead("HKLM\SOFTWARE\Node.js\InstallPath")
  On Error GoTo 0
  If install <> "" Then
    candidate = fso.BuildPath(install, "node.exe")
    If fso.FileExists(candidate) Then ResolveNode = candidate : Exit Function
  End If
  For Each entry In Split(shell.ExpandEnvironmentStrings("%PATH%"), ";")
    entry = Replace(entry, Chr(34), "")
    If entry <> "" Then
      candidate = fso.BuildPath(entry, "node.exe")
      If fso.FileExists(candidate) Then ResolveNode = candidate : Exit Function
    End If
  Next
  ResolveNode = ""
End Function
