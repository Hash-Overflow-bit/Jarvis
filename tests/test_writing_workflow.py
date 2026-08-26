import pytest

from core.writing.pipeline import WritingPipeline, WritingIntent


@pytest.mark.parametrize("prompt, expected", [
    (
        "Investigate AI use in project management, write at least 2k words with sources, and save the document.",
        {"task_type": "research_write", "topic": "AI use in project management", "research_required": True, "sources_required": True, "minimum_words": 2000, "save_required": True, "destination": None, "output_format": "markdown"}
    ),
    (
        "Write a 2000+ word research paper about AI in project management and save it on Desktop.",
        {"task_type": "research_write", "topic": "AI in project management", "research_required": True, "sources_required": False, "minimum_words": 2000, "save_required": True, "destination": "desktop", "output_format": "markdown"}
    ),
    (
        "Research AI's impact on project management, make a detailed sourced report of at least 2000 words, and save it.",
        {"task_type": "research_write", "topic": "AI's impact on project management", "research_required": True, "sources_required": True, "minimum_words": 2000, "save_required": True, "destination": None, "output_format": "markdown"}
    ),
    (
        "Research the latest quantum computing breakthroughs.",
        {"task_type": "research_write", "topic": "the latest quantum computing breakthroughs.", "research_required": True, "sources_required": False, "minimum_words": None, "save_required": False, "destination": None, "output_format": "markdown"}
    ),
    (
        "Save this research on my desktop",
        {"task_type": "research_write", "topic": "save this research on my desktop", "research_required": False, "sources_required": False, "minimum_words": None, "save_required": True, "destination": "desktop", "output_format": "markdown"}
    ),
    (
        "Write a 5k words report on the roman empire and save to a file.",
        {"task_type": "simple", "topic": "roman empire", "research_required": False, "sources_required": False, "minimum_words": 5000, "save_required": True, "destination": None, "output_format": "markdown"}
    ),
    (
        "Investigate climate change, use sources, and write a minimum of 1000 words. Export to report.pdf",
        {"task_type": "research_write", "topic": "climate change", "research_required": True, "sources_required": True, "minimum_words": 1000, "save_required": True, "destination": None, "output_format": "pdf"}
    ),
    (
        "Please investigate the stock market trends and save it.",
        {"task_type": "research_write", "topic": "the stock market trends", "research_required": True, "sources_required": False, "minimum_words": None, "save_required": True, "destination": None, "output_format": "markdown"}
    ),
    (
        "Research space exploration, 3k words with citations, write to desktop.",
        {"task_type": "research_write", "topic": "space exploration", "research_required": True, "sources_required": True, "minimum_words": 3000, "save_required": True, "destination": "desktop", "output_format": "markdown"}
    ),
    (
        "Create file report.md with 1000 words about history.",
        {"task_type": "simple", "topic": "create file report.md with 1000 words about history.", "research_required": False, "sources_required": False, "minimum_words": 1000, "save_required": True, "destination": None, "output_format": "md"}
    ),
    (
        "Tell me about machine learning and save to desktop",
        {"task_type": "simple", "topic": "machine learning", "research_required": False, "sources_required": False, "minimum_words": None, "save_required": True, "destination": "desktop", "output_format": "markdown"}
    ),
    (
        "Research apples, 1500 words, sources required, export to fruits.json on desktop",
        {"task_type": "research_write", "topic": "apples", "research_required": True, "sources_required": True, "minimum_words": 1500, "save_required": True, "destination": "desktop", "output_format": "json"}
    ),
    (
        "Prepare a comprehensive, sourced analysis of AI in supply-chain operations. The document should be no shorter than 2,000 words and should be saved to my Desktop as ai_supply_chain_report.txt",
        {"task_type": "research_write", "topic": "ai in supply-chain operations", "research_required": True, "sources_required": True, "minimum_words": 2000, "save_required": True, "destination": "desktop", "output_format": "txt"}
    ),
    (
        "Produce an evidence-based 1800-word report on AI in healthcare and save it.",
        {"task_type": "research_write", "topic": "ai in healthcare", "research_required": True, "sources_required": True, "minimum_words": 1800, "save_required": True, "destination": None, "output_format": "markdown"}
    ),
    (
        "Create a referenced analysis of automation in accounting, minimum 1500 words, and put it on Desktop.",
        {"task_type": "research_write", "topic": "automation in accounting", "research_required": True, "sources_required": True, "minimum_words": 1500, "save_required": True, "destination": "desktop", "output_format": "markdown"}
    ),
    (
        "Draft a detailed paper on AI cybersecurity using credible sources and save it as cyber_ai.txt.",
        {"task_type": "research_write", "topic": "ai cybersecurity using credible sources", "research_required": True, "sources_required": True, "minimum_words": None, "save_required": True, "destination": None, "output_format": "txt"}
    ),
    (
        "Summarize local_report.md and save it to Desktop",
        {"task_type": "local_doc", "topic": "local_report.md", "research_required": False, "sources_required": False, "minimum_words": None, "save_required": True, "destination": "desktop", "output_format": "md", "source_files": ["local_report.md"]}
    ),
    (
        "Extract all dates from transactions.csv into data.json",
        {"task_type": "extraction", "topic": "all dates from transactions.csv", "research_required": False, "sources_required": False, "minimum_words": None, "save_required": True, "destination": None, "output_format": "json", "source_files": ["transactions.csv"]}
    ),
])
def test_writing_intent_parsing(prompt, expected):
    intent = WritingPipeline.parse_intent(prompt)
    assert isinstance(intent, WritingIntent), "Expected WritingIntent"
    
    # We do a loose check on topic
    extracted_topic = intent.topic.replace('.', '').strip().lower()
    expected_topic = expected["topic"].replace('.', '').strip().lower()
    assert expected_topic in extracted_topic or extracted_topic in expected_topic
    
    assert intent.task_type == expected["task_type"]
    assert intent.research_required == expected["research_required"]
    assert intent.sources_required == expected["sources_required"]
    assert intent.minimum_words == expected["minimum_words"]
    assert intent.save_required == expected["save_required"]
    assert intent.destination == expected["destination"]
    assert intent.output_format == expected["output_format"]
    if "source_files" in expected:
        assert set(intent.source_files or []) == set(expected["source_files"])
    else:
        assert not intent.source_files


def test_direct_route_writing_intent():
    from core.orchestrator.agent_loop import AgentExecutionLoop
    loop = AgentExecutionLoop()
    
    # Test 1: Full research + write + save + words
    prompt = "Investigate AI use in project management, write at least 2k words with sources, and save the document."
    plan = loop._direct_route(prompt)
    
    assert isinstance(plan, list)
    assert len(plan) == 3
    assert plan[0]["tool"] == "web_search"
    assert "project management" in plan[0]["arguments"]["query"]
    
    assert plan[1]["tool"] == "generate_document"
    assert plan[1]["arguments"]["intent"]["minimum_words"] == 2000
    assert plan[1]["arguments"]["intent"]["sources_required"] is True
    
    assert plan[2]["tool"] == "write_file"
    assert plan[2]["arguments"]["content"] == "<USE_GENERATED_ARTIFACT>"
    assert "output.md" in plan[2]["arguments"]["filepath"]

    # Test 2: Cross-turn save
    loop.session_artifacts["last_generated_document"] = {"content": "Test content"}
    plan2 = loop._direct_route("Save this research on my Desktop.")
    assert isinstance(plan2, list)
    assert len(plan2) == 1
    assert plan2[0]["tool"] == "write_file"
    assert plan2[0]["arguments"]["content"] == "<USE_GENERATED_ARTIFACT>"
    assert "Desktop" in plan2[0]["arguments"]["filepath"]
