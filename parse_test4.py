import re
from pathlib import Path

def test_parse(cleaned):
    clauses = re.split(r'\.\s+|\s+then\s+|,?\s*then\s+|\s+and\s+(?=create|make|build|put|read|write|delete)', cleaned, flags=re.IGNORECASE)
    if len(clauses) > 0:
        multi_plan = []
        valid = True
        
        context = {
            "desktop": "/Users/m2air/Desktop",
            "workspace": "/Users/m2air/Desktop/Jarvis"
        }
        last_created_dir = context["desktop"]
        
        for clause in clauses:
            clause = clause.strip()
            if not clause or "do not claim" in clause.lower() or "verify" in clause.lower() and "filesystem" in clause.lower():
                continue
            
            read_m = re.search(r'read\s+(?:the\s+)?(?:file\s+)?(?:back\s+)?(?:and\s+confirm\s+)?(?:the\s+)?(?:exact\s+)?(?:path\s+and\s+)?(?:content\s+)?(?:named\s+|called\s+)?[\'\"]?([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]*)[\'\"]?', clause, re.IGNORECASE)
            read_m_simple = re.search(r'read\s+(?:the\s+)?(?:file\s+)?(?:back)?', clause, re.IGNORECASE)
            
            folder_m = re.search(r'(?:create|make|build|put)\s+(?:a\s+)?(?:new\s+|another\s+)?(?:folder|directory|package)\s+(?:named\s+|called\s+)?[\'\"]?([a-zA-Z0-9_\-\./\\]+)[\'\"]?', clause, re.IGNORECASE)
            if not folder_m:
                folder_m = re.search(r'(?:create|make|build)\s+([a-zA-Z0-9_\-/]+)(?:\s+on\s+desktop)?', clause, re.IGNORECASE)
                
            file_m = re.search(r'(?:create|make|build|put)\s+(?:a\s+)?(?:new\s+|another\s+)?(?:file\s+)?(?:named\s+|called\s+)?[\'\"]?([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]+)[\'\"]?(?:\s+(?:containing|with)\s+(?:exactly\s+)?(?:content\s+)?(.+))?', clause, re.IGNORECASE)
            if not file_m:
                file_m = re.search(r'(?:put|create)\s+([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]+)\s+inside', clause, re.IGNORECASE)

            content_m = re.search(r'containing\s+(?:exactly\s+)?(.+)', clause, re.IGNORECASE)
            
            parent_dir = last_created_dir
            parent_ref_match = re.search(r'(?:inside|under|within|in)\s+(?:it|that folder|that directory|([a-zA-Z0-9_\-\.]+))|there', clause, re.IGNORECASE)
            
            if "inside" in clause.lower() and not parent_ref_match:
                alt_m = re.search(r'inside\s+([a-zA-Z0-9_\-\.]+)', clause, re.IGNORECASE)
                if alt_m:
                    parent_ref_match = alt_m

            if parent_ref_match:
                ref_name = parent_ref_match.group(1)
                if ref_name:
                    ref_name_lower = ref_name.lower()
                    if ref_name_lower in context:
                        parent_dir = context[ref_name_lower]
                    else:
                        for k, v in context.items():
                            if k.endswith(ref_name_lower) or ref_name_lower in k:
                                parent_dir = v
                                break
                else:
                    parent_dir = last_created_dir
            elif "on my desktop" in clause.lower() or "on desktop" in clause.lower():
                parent_dir = context["desktop"]
            
            exts = (".txt", ".md", ".json", ".csv", ".svg", ".py")
            is_file = file_m is not None
            is_folder = folder_m and not (is_file and file_m.group(1).endswith(exts))
            if is_folder and folder_m.group(1).endswith(exts):
                is_folder = False 
                file_m = folder_m
                is_file = True

            matched = False
            if is_folder:
                folder_name = folder_m.group(1).strip()
                is_absolute = folder_name.startswith(("/", "\\")) or ":" in folder_name
                target_dir = str(Path(parent_dir) / folder_name) if not is_absolute else folder_name
                multi_plan.append({"step": len(multi_plan)+1, "tool": "create_directory", "arguments": {"directory": target_dir}})
                context[Path(folder_name).name.lower()] = target_dir
                last_created_dir = target_dir
                matched = True
            elif is_file:
                file_name = file_m.group(1).strip()
                content = ""
                if file_m.lastindex and file_m.lastindex >= 2 and file_m.group(2):
                    content = file_m.group(2).strip()
                elif content_m:
                    content = content_m.group(1).strip()
                if content.endswith("."):
                    content = content[:-1]
                
                is_absolute = file_name.startswith(("/", "\\")) or ":" in file_name
                target_fp = str(Path(parent_dir) / file_name) if not is_absolute else file_name
                multi_plan.append({"step": len(multi_plan)+1, "tool": "write_file", "arguments": {"filepath": target_fp, "content": content}})
                matched = True
            elif read_m:
                file_name = read_m.group(1).strip()
                multi_plan.append({"step": len(multi_plan)+1, "tool": "read_file", "arguments": {"filepath": file_name}})
                matched = True
            elif read_m_simple:
                last_file = ""
                for p in reversed(multi_plan):
                    if p["tool"] == "write_file":
                        last_file = p["arguments"]["filepath"]
                        break
                if last_file:
                    multi_plan.append({"step": len(multi_plan)+1, "tool": "read_file", "arguments": {"filepath": last_file}})
                    matched = True
                else:
                    valid = False
            
            if not matched:
                if any(v in clause.lower() for v in ["create", "write", "delete", "move", "rename", "put"]):
                    valid = False
        
        if valid and len(multi_plan) > 1:
            return multi_plan

prompts = [
    "Create a folder named nested_test on my Desktop. Inside it, create a folder named level1. Inside level1, create another folder named level2. Inside level2, create notes.txt containing exactly Nested filesystem test passed. Then read the file back and verify its exact path and content.",
    "Create A on Desktop. Inside it create B. Inside B create C.",
    "Make project_x. Under project_x create src. Inside src create utils. Put helper.txt there.",
    "Create reports/2026/january and put summary.txt inside january.",
    "Create Alpha. Inside that folder make Beta. There create test.txt."
]

for p in prompts:
    print("\nPROMPT:", p)
    res = test_parse(p)
    if res:
        for s in res: print(s)
    else:
        print("FAILED TO PARSE")
