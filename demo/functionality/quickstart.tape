Output demo/functionality/quickstart.mp4
Source demo/common.tape
Set FontSize 32
Set Height 900
Set TypingSpeed 15ms
Source demo/session.tape

Type "iwant up gpt-oss-20b --infra gcp --yes"
Enter
Wait+Screen /Model ready/
Wait+Line /❯$/
Sleep 2s

Hide
Type "clear"
Enter
Wait+Line /❯$/
Show
Type "# Send your first prompt"
Enter
Type `curl -fsS "$OPENAI_BASE_URL/chat/completions" \`
Enter
Type `  -H "Authorization: Bearer $OPENAI_API_KEY" \`
Enter
Type `  -H "Content-Type: application/json" \`
Enter
Type `  -d '{"model":"openai/gpt-oss-20b","messages":[{"role":"user","content":"Write a haiku about GPUs."}],"max_tokens":256}' \`
Enter
Type `  | python -c 'import json,sys; print(json.load(sys.stdin)["choices"][0]["message"]["content"])'`
Enter
Wait+Screen /Night turns into dawn/
Wait+Line /❯$/
Sleep 4s

Type "iwant down iwant-gpt-oss-20b-v1-a1b2c3"
Enter
Wait+Screen /Cluster removed/
Wait+Line /❯$/
Sleep 3s
