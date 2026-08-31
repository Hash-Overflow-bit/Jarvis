from core.writing.pipeline import WritingPipeline

prompt = "research PSX 2020-2026, top 10 high-performance stocks, top companies, trend after COVID"
intent = WritingPipeline.parse_intent(prompt)
print(f"Task type: {intent.task_type}")
