import shutil
from pathlib import Path
from unittest.mock import patch
import pytest

from server import save_agent_outputs, AGENT_ORDER

def test_save_agent_outputs(tmp_path):
    # We patch Path.parent to redirect the "outputs" root folder to pytest's tmp_path
    mock_base_path = tmp_path
    
    with patch("server.Path") as mock_path_cls:
        # Configure Path(__file__).parent to return mock_base_path
        mock_path_instance = mock_path_cls.return_value
        mock_path_instance.parent = mock_base_path
        
        # Setup mock outputs dict
        mock_outputs = {
            "clarifier": ["Refined query: intermittent fasting in diabetes"],
            "planner": ["Step 1: Search PubMed", "\nStep 2: Search ArXiv"],
            "searcher": [], # Empty list to test fallback behavior
        }
        # Populate other agents with simple text
        for agent in AGENT_ORDER:
            if agent not in mock_outputs:
                mock_outputs[agent] = [f"Mock output for {agent}"]

        session_id = "test_session_123"
        query = "intermittent fasting vs caloric restriction"
        
        # Invoke the save function
        save_agent_outputs(session_id, mock_outputs, query)
        
        # Verify the target session outputs directory was created
        expected_dir = tmp_path / "outputs" / f"session_{session_id}"
        assert expected_dir.exists()
        assert expected_dir.is_dir()
        
        # Verify metadata file exists and has correct content
        meta_file = expected_dir / "00_metadata.md"
        assert meta_file.exists()
        meta_content = meta_file.read_text(encoding="utf-8")
        assert "Research Session Metadata" in meta_content
        assert session_id in meta_content
        assert query in meta_content

        # Verify step files
        for idx, agent_name in enumerate(AGENT_ORDER, 1):
            step_file = expected_dir / f"{idx:02d}_{agent_name}.md"
            assert step_file.exists()
            file_content = step_file.read_text(encoding="utf-8")
            
            # Check title
            assert f"Step {idx}: {agent_name.capitalize()}" in file_content
            
            # Check content
            if agent_name == "searcher":
                assert "No direct text output was recorded" in file_content
            elif agent_name == "clarifier":
                assert "Refined query: intermittent fasting in diabetes" in file_content
            elif agent_name == "planner":
                assert "Step 1: Search PubMed\nStep 2: Search ArXiv" in file_content
            else:
                assert f"Mock output for {agent_name}" in file_content
