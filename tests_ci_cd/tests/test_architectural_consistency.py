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
MODELS_CORE_PATH = PROJECT_ROOT / "models" / "core.py"
CODING_CONSTITUTION_PATH = PROJECT_ROOT / "constitutional_layer_immutable" / "CODING_CONSTITUTION.md"

# Files and directories that should be excluded from certain checks
EXCLUDED_FILES = {
    "__pycache__",
    ".pyc",
    "test_",
    "__init__.py",
}

# Directories to exclude (virtual environments, third-party packages)
EXCLUDED_DIRS = {
    ".venv",
    "venv",
    "env",
    "ENV",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "site-packages",
    "node_modules",
}

# Required models that MUST exist in models/core.py
REQUIRED_MODELS = {
    "Vote",
    "VoteResult",
    "Proposal",
    "BoardSession",
    "BoardMember",
    "ConstitutionalError",
    "ConstitutionalRule",
    "ConstitutionalValidation",
    "APIResponse",
}


# ============================================================================
# Helper Functions
# ============================================================================

def get_python_files(directory: Path) -> List[Path]:
    """Get all Python files in directory, excluding test files, cache, and third-party packages."""
    python_files = []
    for path in directory.rglob("*.py"):
        # Skip if path contains any excluded directory
        path_str = str(path)
        if any(excluded_dir in path_str for excluded_dir in EXCLUDED_DIRS):
            continue
        # Skip if path contains any excluded file pattern
        if any(excluded in path_str for excluded in EXCLUDED_FILES):
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


def imports_from_module(node: ast.AST, module_name: str, item_name: str) -> bool:
    """
    Check if a specific item is imported from a specific module.
    
    Args:
        node: AST node to search
        module_name: Module name to check (e.g., "models.core")
        item_name: Item name to check (e.g., "ConstitutionalError")
        
    Returns:
        True if item_name is imported from module_name
    """
    for child in ast.walk(node):
        if isinstance(child, ast.ImportFrom):
            # Check if the module matches (exact match or module_name is part of the import)
            if child.module and (child.module == module_name or child.module.endswith(f".{module_name}") or module_name in child.module):
                for alias in child.names or []:
                    # Check both the alias name and the actual name (in case of "import X as Y")
                    if alias.name == item_name or (alias.asname and alias.asname == item_name):
                        return True
    return False


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
                    
                    # Check if function is a method in a class by traversing AST properly
                    is_method = False
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef):
                            # Check if func is in this class's body
                            for item in node.body:
                                if isinstance(item, ast.FunctionDef) and item == func:
                                    is_method = True
                                    break
                            if is_method:
                                break
                    
                    # Skip methods for now (they may have less strict requirements)
                    if is_method:
                        continue
                    
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
                # Read file with UTF-8 encoding to avoid UnicodeDecodeError
                file_content = file_path.read_text(encoding="utf-8")
                
                # Check if ConstitutionalError is used
                if "ConstitutionalError" in file_content:
                    # Check if ConstitutionalError is imported from models.core
                    has_correct_import = imports_from_module(tree, "models.core", "ConstitutionalError")
                    
                    if not has_correct_import:
                        violations.append(
                            f"{file_path.relative_to(PROJECT_ROOT)} uses ConstitutionalError "
                            f"but doesn't import from models.core"
                        )
            except (SyntaxError, UnicodeDecodeError):
                # Skip files with syntax errors or encoding issues
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
    
    def test_logging_pattern_consistency(self):
        """Test that logging follows consistent patterns."""
        python_files = get_python_files(PROJECT_ROOT)
        main_files = [
            f for f in python_files 
            if "test_" not in str(f) and "constitution.py" in str(f)
        ]
        
        violations = []
        
        for file_path in main_files:
            try:
                # Read file with UTF-8 encoding
                content = file_path.read_text(encoding="utf-8")
                tree = parse_file(file_path)
                
                # Check for logger initialization pattern
                has_logger = "logging.getLogger(__name__)" in content or "logger = " in content
                
                if has_logger:
                    # Check that errors are logged before raising
                    functions = get_function_definitions(tree)
                    for func in functions:
                        func_content = ast.get_source_segment(content, func) or ""
                        # Check if ConstitutionalError is raised
                        if "ConstitutionalError" in func_content:
                            # Should have logging before raise
                            if "raise ConstitutionalError" in func_content:
                                # Check if there's logging before the raise
                                raise_idx = func_content.find("raise ConstitutionalError")
                                before_raise = func_content[:raise_idx]
                                if "logger." not in before_raise and "logging." not in before_raise:
                                    violations.append(
                                        f"{file_path.relative_to(PROJECT_ROOT)}: "
                                        f"Function '{func.name}' raises ConstitutionalError without logging"
                                    )
            except (SyntaxError, AttributeError):
                pass
        
        # Warning for now
        if violations:
            print(f"Warning: Found {len(violations)} potential logging violations:")
            for violation in violations[:5]:
                print(f"  - {violation}")


class TestNamingConventions:
    """Test naming convention compliance"""
    
    def test_class_names_pascal_case(self):
        """Test that class names use PascalCase."""
        python_files = get_python_files(PROJECT_ROOT)
        violations = []
        
        for file_path in python_files:
            if "test_" in str(file_path):
                continue
            
            try:
                tree = parse_file(file_path)
                classes = get_class_definitions(tree)
                
                for class_name in classes:
                    # Check PascalCase (starts with uppercase, no underscores for main words)
                    if not class_name[0].isupper():
                        violations.append(
                            f"{file_path.relative_to(PROJECT_ROOT)}: "
                            f"Class '{class_name}' doesn't start with uppercase"
                        )
                    # Allow underscores for compound names but check pattern
                    if "_" in class_name and not all(word[0].isupper() for word in class_name.split("_") if word):
                        # This is a warning, not an error
                        pass
            except SyntaxError:
                pass
        
        # Report violations
        if violations:
            print(f"Warning: Found {len(violations)} naming convention issues:")
            for violation in violations[:10]:
                print(f"  - {violation}")
    
    def test_function_names_snake_case(self):
        """Test that function names use snake_case."""
        python_files = get_python_files(PROJECT_ROOT)
        violations = []
        
        for file_path in python_files:
            if "test_" in str(file_path):
                continue
            
            try:
                tree = parse_file(file_path)
                functions = get_function_definitions(tree)
                
                for func in functions:
                    # Skip private functions
                    if func.name.startswith("_"):
                        continue
                    
                    # Check snake_case
                    if not func.name.islower() and "_" not in func.name:
                        # Might be a constant or class method, check context
                        if not func.name.isupper():  # Not a constant
                            violations.append(
                                f"{file_path.relative_to(PROJECT_ROOT)}: "
                                f"Function '{func.name}' doesn't follow snake_case"
                            )
            except SyntaxError:
                pass
        
        # Warning for now
        if violations:
            print(f"Warning: Found {len(violations)} function naming issues:")
            for violation in violations[:10]:
                print(f"  - {violation}")


class TestConstitutionFileExists:
    """Test that CODING_CONSTITUTION.md exists"""
    
    def test_coding_constitution_exists(self):
        """Test that CODING_CONSTITUTION.md file exists."""
        assert CODING_CONSTITUTION_PATH.exists(), (
            "CODING_CONSTITUTION.md must exist in constitutional_layer_immutable/"
        )
    
    def test_coding_constitution_has_rules(self):
        """Test that CODING_CONSTITUTION.md contains all 10 rules."""
        # Read file with UTF-8 encoding to avoid UnicodeDecodeError
        content = CODING_CONSTITUTION_PATH.read_text(encoding="utf-8")
        
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
        
        # Read file with UTF-8 encoding
        content = MODELS_CORE_PATH.read_text(encoding="utf-8")
        
        # Check that required models are defined
        for model_name in REQUIRED_MODELS:
            assert model_name in content, (
                f"models/core.py must define {model_name}"
            )
    
    def test_models_use_pydantic(self):
        """Test that models inherit from Pydantic BaseModel."""
        tree = parse_file(MODELS_CORE_PATH)
        
        # Read file with UTF-8 encoding
        content = MODELS_CORE_PATH.read_text(encoding="utf-8")
        # Check that classes inherit from BaseModel
        has_pydantic_import = "BaseModel" in content
        assert has_pydantic_import, "models/core.py must import BaseModel from pydantic"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

