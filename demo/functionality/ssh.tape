Output demo/functionality/ssh.mp4
Source demo/common.tape
Source demo/session.tape

Type "iwant ssh"
Sleep 500ms
Enter
Wait+Screen /Which instance/
Sleep 2500ms
Enter
Wait+Screen /Connection closed/
Wait+Line /❯$/
Sleep 4s
