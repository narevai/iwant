Output demo/functionality/dry-run.mp4
Source demo/common.tape
Source demo/session.tape

Type "iwant up gpt-oss-20b"
Sleep 500ms
Enter
Wait+Screen /Where do you want to launch/
Sleep 2500ms
Enter
Wait+Screen /On-demand or spot/
Sleep 2500ms
Enter
Wait+Screen /Autostop after/
Sleep 2500ms
Enter
Wait+Screen /Ready to launch/
Sleep 2500ms
Down
Sleep 1500ms
Enter
Wait+Screen /Launch plan/
Wait+Line /❯$/
Sleep 4s
