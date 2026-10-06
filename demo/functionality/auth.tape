Output demo/functionality/auth.mp4
Source demo/common.tape
Env IWANT_DEMO_SCENE "auth-unconfigured"
Source demo/session.tape

Type "iwant auth"
Sleep 500ms
Enter
Wait+Screen /Pick a cloud/
Sleep 800ms
Enter
Wait+Screen /application-default login/
Wait+Line /❯$/
Sleep 3s

Hide
Type "export IWANT_DEMO_SCENE=auth; clear"
Enter
Wait+Line /❯$/
Show

Type "iwant auth"
Sleep 500ms
Enter
Wait+Screen /Pick a cloud/
Sleep 800ms
Enter
Wait+Screen /GCP is ready/
Wait+Line /❯$/
Sleep 4s
