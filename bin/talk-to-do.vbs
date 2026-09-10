' Talk to D.O. - one click, no terminal.
' Pops a box, drops your message in his inbox. The running organism picks it up
' on its next cycle and speaks the reply aloud. If he is not running, the message
' waits for him - state persists.
Set fso = CreateObject("Scripting.FileSystemObject")
' this script lives in DO\bin\ ; inbox is DO\var\inbox.txt
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
root = fso.GetParentFolderName(scriptDir)
inbox = root & "\var\inbox.txt"
msg = InputBox("Say something to D.O." & vbCrLf & vbCrLf & _
               "He will speak his reply aloud within a few seconds.", "Talk to D.O.")
If msg <> "" Then
    Set f = fso.OpenTextFile(inbox, 8, True)  ' 8 = append, True = create
    f.WriteLine msg
    f.Close
End If
