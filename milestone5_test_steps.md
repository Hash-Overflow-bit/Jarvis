# Milestone 5 & Kokoro TTS Manual Testing Steps

This guide outlines the step-by-step instructions to manually verify the **Core Agent Execution Loop** and **Kokoro TTS (bf_emma)** voice streaming upgrades.

---

## 📋 Prerequisites

Ensure that:
1. **Ollama** is running locally and has the `llama3.1` model (or `qwen2.5:7b-instruct` on the client PC) downloaded.
2. The virtual environment is active and all packages are updated:
   ```bash
   poetry install
   ```
3. Run the Kokoro voice asset downloader:
   ```bash
   poetry run python scripts/download_kokoro_models.py
   ```
   *Verify that `kokoro-v1.0.onnx` and `voices-v1.0.bin` exist inside your project's `models/` directory.*

4. Ensure your `.env` contains the Kokoro engine setting:
   ```ini
   TTS_ENGINE=kokoro
   KOKORO_VOICE_MODEL=kokoro-v1.0.onnx
   KOKORO_VOICES_FILE=voices-v1.0.bin
   KOKORO_VOICE_ID=bf_emma
   KOKORO_LANG_CODE=b
   ```

---

## 🚀 Step 1: Launch Jarvis in Text/Voice Mode

Start Jarvis in interactive mode:
```bash
poetry run python main.py --mode text
```
*(Use `--mode audio` if you have voice input/output hardware connected).*

---

## 🧪 Step 2: Run the Manual Test Cases

Copy and paste the prompts below into the Jarvis prompt window to verify execution:

### 1. Multi-Step Task Planning
*   **Prompt**: 
    > `"Create a folder named M5_test inside my sandbox, and inside it write a file named details.txt saying Hello from Milestone Five."`
*   **Expected Behavior**:
    1. **Planning**: Jarvis prints: `[📋 Plan] Decomposed into 2 steps:`
       - Step 1: `create_directory` with arguments pointing to `sandbox/M5_test`
       - Step 2: `write_file` with arguments pointing to `sandbox/M5_test/details.txt`
    2. **Execution**: Jarvis runs Step 1:
       - Displays safety approval warnings.
       - Confirm by typing `yes` and hitting Enter.
       - Runs Step 2: Confirm by typing `yes` again.
    3. **Immediate Speakback**: Jarvis streams the final synthesized confirmation voice (`bf_emma`) chunk-by-chunk in real-time.
    4. **Verification**: Open `sandbox/M5_test/details.txt` on your machine and confirm it contains the text.

### 2. Self-Correction & Reflection Loop
*   **Prompt**: 
    > `"Write the word 'Test' to a file at /etc/unauthorized.txt, and if that fails, write it to my sandbox folder at /Users/m2air/Desktop/Jarvis/sandbox/fixed.txt instead."`
    *(Note: Replace the sandbox path with your actual `SANDBOX_ROOTS` path if testing on Windows).*
*   **Expected Behavior**:
    1. **Plan & Execution (Attempt 1)**: Jarvis attempts to write to `/etc/unauthorized.txt` first.
    2. **Failure Capture**: The sandbox enforcer blocks the write action and returns a `PermissionError`.
    3. **Reflection**: Jarvis prints `[❌ Failure] Step 1 failed: PermissionError`.
    4. **Re-planning**: Jarvis reflects on the error trace, prints `[🔄 Re-planning] Self-corrected! Revised remaining steps:`, and updates the destination path to the allowed sandbox folder automatically.
    5. **Retry**: Runs the revised step. Once approved, the file `sandbox/fixed.txt` is created successfully.

### 3. Voice Streaming Low-Latency
*   **Prompt**: 
    > `"Say a long paragraph explaining the solar system."`
*   **Expected Behavior**:
    - Jarvis should start speaking the British female voice (`bf_emma`) **instantly** (word-by-word streaming) as the text is generated, rather than making you wait for the full paragraph to compile.
