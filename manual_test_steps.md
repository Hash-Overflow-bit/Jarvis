# Milestone 2 Manual Testing Steps

This guide outlines the step-by-step instructions to manually verify the Milestone 2 (M2) tools and security sandbox enforcer.

---

## Prerequisites

Before starting, ensure that:
1. **Ollama** is running locally:
   ```bash
   ollama serve
   ```
2. The **Llama 3.1** model is downloaded:
   ```bash
   ollama pull llama3.1
   ```
3. Project dependencies are installed and the virtual environment is ready:
   ```bash
   poetry install
   ```

---

## Step 1: Set Up the Test Sandbox Environment

Run these commands in your terminal to set up a clean, predictable sandbox structure containing dummy files for testing:

```bash
# Ensure you are at the project root (/Users/m2air/Desktop/Jarvis)
cd /Users/m2air/Desktop/Jarvis

# Create sandbox folder structure
mkdir -p sandbox/test_logs/nested_logs

# Create some dummy files of various types and sizes
echo "Normal application log entry." > sandbox/test_logs/info.log
echo "CRITICAL ERROR: Connection failure." > sandbox/test_logs/error.log
echo "Temp content" > sandbox/test_logs/nested_logs/temp.tmp
echo "Project documentation" > sandbox/readme.txt
```

Verify that `.env` contains the correct `SANDBOX_ROOTS` configuration pointing to your absolute sandbox path:
```ini
SANDBOX_ROOTS=/Users/m2air/Desktop/Jarvis/sandbox
```

---

## Step 2: Launch Jarvis in Text Mode

Run Jarvis in interactive text-only mode:
```bash
poetry run python main.py --mode text
```

You should see a banner indicating that Ollama is connected:
```
J A R V I S
Local AI Assistant | Powered by Ollama
Model: llama3.1 | OS: macos
```

---

## Step 3: Run the Test Scenarios

Interact with Jarvis by typing the following commands at the prompt:

### Scenario A: Directory Audit (Tree View)
*   **Prompt**: `Show me the folder structure of /Users/m2air/Desktop/Jarvis/sandbox`
*   **Expected Behavior**: 
    - Jarvis should invoke the `directory_audit` tool.
    - It should display a tree representation showing the `test_logs` folder, the files `info.log`, `error.log`, and `readme.txt`, and the nested `nested_logs/temp.tmp` structure.

### Scenario B: File Scanner (Listing & Filtering)
*   **Prompt**: `List all files in /Users/m2air/Desktop/Jarvis/sandbox`
*   **Expected Behavior**:
    - Jarvis should invoke the `file_scanner` tool.
    - It should list all 4 files with their sizes and paths.
*   **Prompt**: `Show me only the log files in /Users/m2air/Desktop/Jarvis/sandbox`
*   **Expected Behavior**:
    - Jarvis should invoke the `file_scanner` tool with `extension_filter=".log"`.
    - It should only list `info.log` and `error.log`.

### Scenario C: Sandbox Enforcer (Security Boundary Check)
*   **Prompt**: `List the files in /etc`
*   **Expected Behavior**:
    - Jarvis should attempt to execute the tool, but the `SandboxEnforcer` must intercept it.
    - Jarvis should return a polite security message stating that the path `/etc` is outside the allowed sandbox roots.
*   **Prompt**: `Show the directory tree of /Users/m2air/Desktop/Jarvis/sandbox/../..`
*   **Expected Behavior**:
    - The enforcer resolves the relative path (pointing to `/Users/m2air/Desktop`) and detects the sandbox escape.
    - It must reject it and block access.

### Scenario D: File Cleanup (Moving to Trash)
*   **Prompt**: `Clean up all log files in /Users/m2air/Desktop/Jarvis/sandbox`
*   **Expected Behavior**:
    - Jarvis should invoke the `file_cleanup` tool with `extension_filter=".log"`.
    - It should confirm that 2 files (`info.log` and `error.log`) have been moved to the trash.
*   **Manual Verification**:
    - Check your macOS Trash bin or the fallback folder `sandbox/.jarvis_trash/` to confirm that `info.log` and `error.log` were moved there.
    - Verify that `readme.txt` and `nested_logs/temp.tmp` remain intact in the sandbox directory.
