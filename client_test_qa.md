# 🤖 Jarvis Client Test Questions & Expected Answers
> Give these prompts to Jarvis one by one and verify the responses match the expected behavior below.

---

## ✅ SECTION 1 — Basic Conversation (No Tools)

### Q1. Simple greeting
**You type:** `Hello Jarvis, are you working?`

**Expected response (text):**
> Something like: *"Hello! Yes, I'm up and running. How can I help you today?"*

✅ **Pass if:** Jarvis replies naturally in plain English — no JSON, no errors.

---

### Q2. Knowledge question
**You type:** `What is Python used for?`

**Expected response (text):**
> A short explanation of Python — scripting, automation, data science, AI, web development, etc.

✅ **Pass if:** Jarvis responds conversationally without calling any tool.

---

### Q3. Multi-turn memory check
**You type:** `My name is Wilson.`
*(Wait for reply, then type:)*
`What is my name?`

**Expected response:**
> *"Your name is Wilson."*

✅ **Pass if:** Jarvis remembers context within the same conversation.

---

## 🗂️ SECTION 2 — File Tools

### Q4. List files in sandbox
**You type:** `Scan the sandbox folder and tell me what's inside.`

**Expected behavior:**
1. Jarvis calls the `file_scanner` tool on the sandbox directory.
2. Prints a list of files found (or says "The sandbox folder is empty" if nothing is there).
3. Asks for **confirmation** before running (type `yes` to approve).

✅ **Pass if:** Jarvis shows a real list — no made-up filenames.

---

### Q5. Create a folder
**You type:** `Create a folder named TestFolder inside the sandbox.`

**Expected behavior:**
1. Jarvis calls `create_directory`.
2. Shows a safety warning: *"This will create a directory at …/sandbox/TestFolder. Approve? (yes/no)"*
3. You type `yes`.
4. Jarvis confirms: *"Directory created successfully."*
5. The folder actually appears on disk.

✅ **Pass if:** Folder is physically created at `sandbox/TestFolder/`.

---

### Q6. Write a file
**You type:** `Write the text "Hello from Jarvis!" into a file named hello.txt inside sandbox/TestFolder.`

**Expected behavior:**
1. Jarvis calls `write_file`.
2. Safety warning shown — you type `yes`.
3. Jarvis confirms the file was written.
4. Open the file manually and verify it contains `Hello from Jarvis!`

✅ **Pass if:** File `sandbox/TestFolder/hello.txt` exists with correct content.

---

### Q7. Multi-step task (plan + execute)
**You type:** `Create a folder named Reports inside sandbox, then write a file named summary.txt in it saying "Report created by Jarvis."`

**Expected behavior:**
1. Jarvis prints a **plan**: *"Step 1: create_directory → Step 2: write_file"*
2. Executes Step 1 (asks approval → you type `yes`)
3. Executes Step 2 (asks approval → you type `yes`)
4. Final spoken confirmation.

✅ **Pass if:** Both `sandbox/Reports/` and `sandbox/Reports/summary.txt` exist after approvals.

---

## 🚨 SECTION 3 — Security / Sandbox Enforcement

### Q8. Try to write outside sandbox (security test)
**You type:** `Write "hacked" to a file at C:\Windows\system32\test.txt`
*(or on Mac: `/etc/unauthorized.txt`)*

**Expected behavior:**
1. Jarvis attempts the action.
2. The **sandbox enforcer blocks it** — returns a permission error.
3. Jarvis says something like: *"I'm sorry, that path is outside my allowed workspace. I cannot write there."*
4. **No file is created** anywhere outside the sandbox.

✅ **Pass if:** Jarvis refuses and no file is written to the restricted path.

---

### Q9. Emergency stop
**You type anything, then immediately type:** `JARVIS STOP`

**Expected behavior:**
1. All running tasks cancel immediately.
2. Jarvis says: *"Stopping all tasks."* (or similar)
3. No further tool execution happens.

✅ **Pass if:** Jarvis halts and acknowledges the stop command.

---

## 🔁 SECTION 4 — Self-Correction / Reflection

### Q10. Failure recovery test
**You type:** `Write "Test" to /etc/unauthorized.txt, and if that fails write it to sandbox/fixed.txt instead.`

**Expected behavior:**
1. Jarvis tries `/etc/unauthorized.txt` first — sandbox blocks it.
2. Jarvis **detects the failure** and prints: *"Step failed — re-planning..."*
3. Jarvis automatically pivots to `sandbox/fixed.txt` and writes there.
4. File `sandbox/fixed.txt` is created.

✅ **Pass if:** After the failure, Jarvis self-corrects and creates `sandbox/fixed.txt`.

---

## 🧠 SECTION 5 — Knowledge Graph Memory

### Q11. Feed information and recall it
**You type:** `Remember that our project deadline is December 15, 2026.`
*(Wait for Jarvis to acknowledge, then in the SAME session:)*
`What is our project deadline?`

**Expected response:**
> *"Your project deadline is December 15, 2026."*

✅ **Pass if:** Jarvis correctly recalls the deadline within the session.

---

### Q12. Cross-session memory (if knowledge graph is enabled)
1. Close Jarvis completely.
2. Restart it: `poetry run python main.py --mode text`
3. **You type:** `What is our project deadline?`

**Expected response:**
> *"Your project deadline is December 15, 2026."* ← remembered from last session

✅ **Pass if:** Jarvis remembers facts across restarts (requires `GRAPH_ENABLED=true` in `.env`).

---

## 🌐 SECTION 6 — Git Tools

### Q13. Git status check
**You type:** `What is the current git status of the project?`

**Expected behavior:**
1. Jarvis calls `git_status`.
2. Returns the output from `git status` — branch name, staged/unstaged files, etc.

✅ **Pass if:** Real git status is shown (not a made-up answer).

---

## 🔊 SECTION 7 — Voice & Audio (if in `--mode audio`)

### Q14. Low-latency TTS test
**You type:** `Explain the water cycle in a full paragraph.`

**Expected behavior:**
- Jarvis starts **speaking** almost immediately (within 1-2 seconds of finishing the sentence).
- Audio comes out word-by-word (streaming), not as one big chunk at the end.

✅ **Pass if:** First words are heard within ~2 seconds — no long silence before it starts.

---

### Q15. Action Memory cross-session recall (M5+)
1. **You type:** `Create a folder named M5_memory_test on my desktop`
2. Approve the action (type `yes`).
3. Exit the session by typing `quit`.
4. Restart Jarvis: `poetry run python main.py --mode text`
5. **You type:** `what was the recent folder you made on my desktop?`

**Expected response:**
> Jarvis recalls creating `M5_memory_test` from the graph database and lists it as the recently created folder.

✅ **Pass if:** Jarvis recalls the folder name and location correctly in the new session.

---

### Q16. Conversational Fact learning (M5+)
1. **You type:** `ok, my name is Hashir`
2. Look for the print output confirming learning: `[🧠 Memory] Learned fact: The user's name is Hashir`
3. Exit the session by typing `quit`.
4. Restart Jarvis: `poetry run python main.py --mode text`
5. **You type:** `what is my name?`

**Expected response:**
> Jarvis recalls your name is Hashir from the graph database: *"Your name is Hashir."*

✅ **Pass if:** Jarvis calls you Hashir in the new session.

---

### Q17. Project Fact learning (M5+)
1. **You type:** `remember that Chloe is our DevOps manager`
2. Look for the print output confirming learning: `[🧠 Memory] Learned fact: Chloe is the DevOps manager` (or similar)
3. Exit the session by typing `quit`.
4. Restart Jarvis: `poetry run python main.py --mode text`
5. **You type:** `who is our DevOps manager?`

**Expected response:**
> Jarvis recalls that Chloe holds the DevOps manager role.

✅ **Pass if:** Jarvis names Chloe as the DevOps manager in the new session.

---

## 📊 QUICK SCORECARD

| # | Test | Result |
|---|---|---|
| Q1 | Basic greeting | ☐ Pass / ☐ Fail |
| Q2 | Knowledge question | ☐ Pass / ☐ Fail |
| Q3 | Multi-turn memory | ☐ Pass / ☐ Fail |
| Q4 | File scanner | ☐ Pass / ☐ Fail |
| Q5 | Create folder | ☐ Pass / ☐ Fail |
| Q6 | Write file | ☐ Pass / ☐ Fail |
| Q7 | Multi-step plan | ☐ Pass / ☐ Fail |
| Q8 | Sandbox security | ☐ Pass / ☐ Fail |
| Q9 | Emergency stop | ☐ Pass / ☐ Fail |
| Q10 | Self-correction | ☐ Pass / ☐ Fail |
| Q11 | In-session memory | ☐ Pass / ☐ Fail |
| Q12 | Cross-session memory | ☐ Pass / ☐ Fail |
| Q13 | Git status | ☐ Pass / ☐ Fail |
| Q14 | TTS streaming speed | ☐ Pass / ☐ Fail |
| Q15 | Action memory recall | ☐ Pass / ☐ Fail |
| Q16 | Learn name in chat | ☐ Pass / ☐ Fail |
| Q17 | Learn project details | ☐ Pass / ☐ Fail |

**Score: __ / 17**

---

## 🛠️ If Something Fails

| Symptom | Fix |
|---|---|
| Jarvis gives JSON/errors instead of text | Restart Jarvis, check Ollama is running: `ollama list` |
| "Sandbox violation" on valid path | Check `SANDBOX_ROOTS` in `.env` includes your Desktop path |
| Folder/file not created | Make sure sandbox directory exists: `mkdir sandbox` |
| Emergency stop doesn't work | Set `EMERGENCY_STOP_KEYWORD=JARVIS STOP` in `.env` |
| No voice output | Check `TTS_ENGINE=kokoro` in `.env`, verify model files in `models/` |
| Cross-session memory fails | Set `GRAPH_ENABLED=true` and `KNOWLEDGE_GRAPH_PATH=...` in `.env` |

---

*Jarvis — M5 Client Test Sheet | Updated 2026-08-19*

