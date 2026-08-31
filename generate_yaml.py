import yaml
cases = []
categories = ["parsing", "end_to_end", "safety", "extraction", "creative"]
for i in range(1, 51):
    cases.append({
        "id": f"case_{i}",
        "prompt": f"Test prompt number {i} for category {categories[i%5]}.",
        "type": categories[i%5]
    })
with open("benchmarks/local_model_cases.yaml", "w") as f:
    yaml.dump({"cases": cases}, f, default_flow_style=False)
