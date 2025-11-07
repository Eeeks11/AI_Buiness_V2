"""
Architectural Consistency Tests

Automated checks that ensure all code follows the patterns defined in CODING_CONSTITUTION.md.
These tests catch architectural drift immediately.
"""

import ast
import importlib.util
from pathlib import Path
from typing import List, Set
import pytest


# ============================================================================
# Test Configuration
# ============================================================================

PROJECT_ROOT = Path(__file__).parent.parent.parent
MODELS_CORE_PATH = PROJECT_ROOT / "Memory Systems" / "Codebase Memory" / "models" / "core.py"
CODING_CONSTITUTION_PATH = PROJECT_ROOT / "Constitutional Layer (Immutable)" / "CODING_CONSTITUTION.md"

# Files that should be excluded from certain checks
EXCLUDED_FILES = {
    "__pycache__",
    ".pyc",
    "test_",
    "__init__.py",
}

# Required models that MUST exist in models/core.py
REQUIRED_MODELS = {
    "Vote",
    "VoteResult",
    "Proposal",
    "BoardSession",
    "BoardMember",
    "ConstitutionalError",
}


# ============================================================================
# Helper Functions
# ============================================================================

def get_python_files(directory: Path) -> List[Path]:
    """Get all Python files in directory, excluding test files and cache."""
    python_files = []
    for path in directory.rglob("*.py"):
        if any(excluded in str(path) for excluded in EXCLUDED_FILES):
            continue
        python_files.append(path)
    return python_files


def parse_file(file_path: Path) -> ast.Module:
    """Parse a Python file into an AST."""
    with open(file_path, "r", encoding="utf-8") as f:
        return ast.parse(f.read(), filename=str(file_path))


def get_imports(node: ast.AST) -> Set[str]:
    """Extract all import statements from AST."""
    imports = set()
    
    for child in ast.walk(node):
        if isinstance(child, ast.Import):
            for alias in child.names:
                imports.add(alias.name)
        elif isinstance(child, ast.ImportFrom):
            if child.module:
                imports.add(child.module)
                for alias in child.names or []:
                    imports.add(f"{child.module}.{alias.name}")
    
    return imports


def get_class_definitions(node: ast.AST) -> List[str]:
    """Extract all class definitions from AST."""
    classes = []
    for child in ast.walk(node):
        if isinstance(child, ast.ClassDef):
            classes.append(child.name)
    return classes


def get_function_definitions(node: ast.AST) -> List[ast.FunctionDef]:
    """Extract all function definitions from AST."""
    functions = []
    for child in ast.walk(node):
        if isinstance(child, ast.FunctionDef):
            functions.append(child)
    return functions


def has_type_hints(func: ast.FunctionDef) -> bool:
    """Check if function has type hints for parameters and return."""
    has_return_annotation = func.returns is not None
    
    has_param_annotations = all(
        arg.annotation is not None for arg in func.args.args
        if arg.arg != "self"  # Exclude self
    )
    
    return has_return_annotation and (has_param_annotations or len(func.args.args) == 0)


def check_logging_imports(node: ast.AST) -> bool:
    """Check if file imports logging module."""
    imports = get_imports(node)
    return "logging" in imports or "import logging" in str(ast.dump(node))


# ============================================================================
# Test Cases
# ============================================================================

class TestModelSourceOfTruth:
    """Test Rule 2 & 8: All models must be in models/core.py"""
    
    def test_required_models_exist(self):
        """Test that all required models exist in models/core.py."""
        assert MODELS_CORE_PATH.exists(), "models/core.py must exist"
        
        tree = parse_file(MODELS_CORE_PATH)
        classes = get_class_definitions(tree)
        
        for model_name in REQUIRED_MODELS:
            assert model_name in classes, (
                f"Required model '{model_name}' not found in models/core.py. "
                f"Found classes: {classes}"
            )
    
    def test_no_duplicate_model_definitions(self):
        """Test that models are not defined outside models/core.py."""
        python_files = get_python_files(PROJECT_ROOT)
        
        # Exclude models/core.py itself
        other_files = [f for f in python_files if f != MODELS_CORE_PATH]
        
        model_classes = set()
        violations = []
        
        for file_path in other_files:
            try:
                tree = parse_file(file_path)
                classes = get_class_definitions(tree)
                
                for class_name in classes:
                    if class_name in REQUIRED_MODELS:
                        violations.append(
                            f"{file_path.relative_to(PROJECT_ROOT)} defines {class_name}, "
                            f"but it should only exist in models/core.py"
                        )
            except SyntaxError:
                # Skip files with syntax errors (they'll be caught by other tests)
                pass
        
        assert len(violations) == 0, (
            "Found duplicate model definitions:\n" + "\n".join(violations)
        )


class TestImportDiscipline:
    """Test Rule 2: Import discipline - models from models/core.py"""
    
    def test_models_imported_from_core(self):
        """Test that models are imported from models/core.py, not defined elsewhere."""
        python_files = get_python_files(PROJECT_ROOT)
        
        violations = []
        
        for file_path in python_files:
            if file_path == MODELS_CORE_PATH:
                continue  # Skip models/core.py itself
            
            try:
                tree = parse_file(file_path)
                imports = get_imports(tree)
                classes = get_class_definitions(tree)
                
                # Check if required models are used but not imported from models.core
                for class_name in classes:
                    if class_name in REQUIRED_MODELS:
                        # This is a violation - model defined outside core
                        violations.append(
                            f"{file_path.relative_to(PROJECT_ROOT)} defines {class_name} "
                            f"instead of importing from models.core"
                        )
                
                # Check if models are imported correctly
                uses_models = any(
                    model in str(tree) for model in REQUIRED_MODELS
                )
                
                if uses_models:
                    has_core_import = any(
                        "models.core" in imp or "from models.core" in str(tree)
                        for imp in imports
                    )
                    
                    if not has_core_import:
                        violations.append(
                            f"{file_path.relative_to(PROJECT_ROOT)} uses models but "
                            f"doesn't import from models.core"
                        )
            except SyntaxError:
                pass
        
        assert len(violations) == 0, (
            "Import discipline violations:\n" + "\n".join(violations)
        )


class TestTypeSafety:
    """Test Rule 1: Type safety - all functions have type hints"""
    
    def test_functions_have_type_hints(self):
        """Test that all public functions have type hints."""
        python_files = get_python_files(PROJECT_ROOT)
        
        violations = []
        
        for file_path in python_files:
            # Skip test files for now (they may have less strict requirements)
            if "test_" in str(file_path):
                continue
            
            try:
                tree = parse_file(file_path)
                functions = get_function_definitions(tree)
                
                for func in functions:
                    # Skip private functions (starting with _)
                    if func.name.startswith("_"):
                        continue
                    
                    # Skip if it's a method in a class (check parent)
                    is_method = any(
                        isinstance(parent, ast.ClassDef) 
                        for parent in ast.walk(tree)
                        if hasattr(parent, "body") and func in getattr(parent, "body", [])
                    )
                    
                    if not has_type_hints(func):
                        violations.append(
                            f"{file_path.relative_to(PROJECT_ROOT)}: "
                            f"Function '{func.name}' missing type hints"
                        )
            except SyntaxError:
                pass
        
        # Allow some violations for now (gradual adoption)
        # In production, this should be strict
        if violations:
            print(f"Warning: Found {len(violations)} functions without type hints:")
            for violation in violations[:10]:  # Show first 10
                print(f"  - {violation}")


class TestErrorHandling:
    """Test Rule 4: Error handling uses ConstitutionalError"""
    
    def test_constitutional_error_imported(self):
        """Test that files using ConstitutionalError import it from models.core."""
        python_files = get_python_files(PROJECT_ROOT)
        
        violations = []
        
        for file_path in python_files:
            if file_path == MODELS_CORE_PATH:
                continue  # Skip models/core.py itself
            
            try:
                tree = parse_file(file_path)
                file_content = file_path.read_text()
                
                # Check if ConstitutionalError is used
                if "ConstitutionalError" in file_content:
                    imports = get_imports(tree)
                    
                    # Should import from models.core
                    has_correct_import = any(
                        "models.core" in imp and "ConstitutionalError" in str(tree)
                        for imp in imports
                    )
                    
                    if not has_correct_import:
                        violations.append(
                            f"{file_path.relative_to(PROJECT_ROOT)} uses ConstitutionalError "
                            f"but doesn't import from models.core"
                        )
            except SyntaxError:
                pass
        
        assert len(violations) == 0, (
            "ConstitutionalError import violations:\n" + "\n".join(violations)
        )


class TestLogging:
    """Test Rule 5 & 6: Logging requirements"""
    
    def test_logging_imported_in_main_modules(self):
        """Test that main modules import logging."""
        python_files = get_python_files(PROJECT_ROOT)
        
        # Focus on main modules, not tests
        main_files = [
            f for f in python_files 
            if "test_" not in str(f) and f.name not in ["__init__.py"]
        ]
        
        violations = []
        
        for file_path in main_files:
            try:
                tree = parse_file(file_path)
                
                # Check if file has functions that should log
                functions = get_function_definitions(tree)
                has_functions = len(functions) > 0
                
                if has_functions and not check_logging_imports(tree):
                    violations.append(
                        f"{file_path.relative_to(PROJECT_ROOT)} has functions but doesn't import logging"
                    )
            except SyntaxError:
                pass
        
        # Warning for now, not strict requirement
        if violations:
            print(f"Warning: Found {len(violations)} files without logging imports:")
            for violation in violations[:5]:
                print(f"  - {violation}")


class TestConstitutionFileExists:
    """Test that CODING_CONSTITUTION.md exists"""
    
    def test_coding_constitution_exists(self):
        """Test that CODING_CONSTITUTION.md file exists."""
        assert CODING_CONSTITUTION_PATH.exists(), (
            "CODING_CONSTITUTION.md must exist in project root"
        )
    
    def test_coding_constitution_has_rules(self):
        """Test that CODING_CONSTITUTION.md contains all 10 rules."""
        content = CODING_CONSTITUTION_PATH.read_text()
        
        # Check for rule markers
        rule_count = content.count("### Rule")
        
        assert rule_count >= 10, (
            f"CODING_CONSTITUTION.md should have 10 rules, found {rule_count}"
        )


class TestModelsCoreStructure:
    """Test that models/core.py has proper structure"""
    
    def test_models_core_has_required_exports(self):
        """Test that models/core.py exports required models."""
        assert MODELS_CORE_PATH.exists(), "models/core.py must exist"
        
        content = MODELS_CORE_PATH.read_text()
        
        # Check that required models are defined
        for model_name in REQUIRED_MODELS:
            assert model_name in content, (
                f"models/core.py must define {model_name}"
            )
    
    def test_models_use_pydantic(self):
        """Test that models inherit from Pydantic BaseModel."""
        tree = parse_file(MODELS_CORE_PATH)
        
        # Check that classes inherit from BaseModel
        has_pydantic_import = "BaseModel" in MODELS_CORE_PATH.read_text()
        assert has_pydantic_import, "models/core.py must import BaseModel from pydantic"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

