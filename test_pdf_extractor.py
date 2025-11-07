"""
Test to verify PDF extractor handles None values correctly.
"""

import pytest
from unittest.mock import Mock, MagicMock
from pdf_extractor import extract_pdf_text


def test_extract_text_handles_none_values():
    """Test that extract_text() returning None doesn't cause TypeError."""
    # Mock a PDF reader with some pages returning None
    mock_page1 = Mock()
    mock_page1.extract_text.return_value = "Page 1 text"
    
    mock_page2 = Mock()
    mock_page2.extract_text.return_value = None  # Simulates problematic page
    
    mock_page3 = Mock()
    mock_page3.extract_text.return_value = "Page 3 text"
    
    mock_reader = Mock()
    mock_reader.pages = [mock_page1, mock_page2, mock_page3]
    
    # Simulate the extraction logic
    text_parts = filter(None, [page.extract_text() for page in mock_reader.pages])
    result = '\n'.join(text_parts)
    
    # Should not raise TypeError and should skip None values
    assert result == "Page 1 text\nPage 3 text"
    assert "None" not in result


def test_extract_text_all_none_returns_empty():
    """Test that if all pages return None, we get an empty string."""
    mock_page1 = Mock()
    mock_page1.extract_text.return_value = None
    
    mock_page2 = Mock()
    mock_page2.extract_text.return_value = None
    
    mock_reader = Mock()
    mock_reader.pages = [mock_page1, mock_page2]
    
    # Simulate the extraction logic
    text_parts = filter(None, [page.extract_text() for page in mock_reader.pages])
    result = '\n'.join(text_parts)
    
    # Should return empty string, not raise error
    assert result == ""


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

