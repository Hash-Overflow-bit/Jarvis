import os
import pytest
from pathlib import Path
from core.config import settings
from unittest.mock import patch

@pytest.fixture(autouse=True)
def isolate_test_memory(tmp_path):
    """
    Ensure every test uses an isolated memory database so long-term state never leaks.
    This protects the live graph.db and prevents tests from sharing transient paths.
    """
    # We create a new isolated graph database for each test in its tmp_path
    temp_db = tmp_path / "test_graph.db"
    
    from core.memory.build_graph import init_db
    init_db(temp_db)
    
    local_memory_db = tmp_path / "local_memory.db"
    with patch.object(settings.__class__, 'knowledge_graph_path', property(lambda self: str(temp_db))), \
         patch.dict(os.environ, {"LOCAL_MEMORY_PATH": str(local_memory_db)}):
        yield
