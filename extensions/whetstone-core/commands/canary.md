---
description: "Internal step of a Whetstone run; do not run it directly (to review a change, use speckit-whetstone-core-review). Run the lockdown canary: show that commands an agent runs cannot write the repository"
---

# Lockdown canary

Run exactly this one command, with no other command before or after it:

```
python3 .specify/extensions/whetstone-core/scripts/canary.py $ARGUMENTS
```

Then reply with the one line it printed, exactly as printed, and nothing else:
no code fence, no explanation. Do not create, edit or delete any file yourself.
A program compares your reply with what the script must print.
