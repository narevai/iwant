Output demo/functionality/down.mp4
Source demo/common.tape
Source demo/session.tape

Type "iwant down"
Sleep 500ms
Enter
Wait+Screen /Which instance/
Sleep 800ms
Enter
Wait+Screen /Cluster removed/
Wait+Line /❯$/
Sleep 2s

Hide
Type "clear"
Enter
Wait+Line /❯$/
Show

Type "iwant list"
Sleep 500ms
Enter
Wait+Screen /No clusters found/
Wait+Line /❯$/
Sleep 4s
