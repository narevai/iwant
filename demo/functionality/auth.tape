Output demo/functionality/auth.mp4
Source demo/common.tape
Env IWANT_DEMO_SCENE "auth-unconfigured"
Source demo/session.tape

Type "iwant auth"
Sleep 500ms
Enter
Wait+Screen /Pick a cloud/
Sleep 2500ms
Enter
Wait+Screen /gcp: not set up yet/
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
Sleep 2500ms
Enter
Wait+Screen /GCP is ready/
Wait+Line /❯$/
Sleep 4s
