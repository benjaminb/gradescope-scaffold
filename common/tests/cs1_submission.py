# Helper functions for autograder unit tests
import ast
import subprocess
import os
import sys
import inspect
import shutil
import textwrap
import unittest

from contextlib import contextmanager
from dotenv import load_dotenv
from importlib import import_module
from io import StringIO
from openai import OpenAI
from pathlib import Path
from typing import cast
from gradescope_utils.autograder_utils.decorators import weight, visibility
from gradescope_utils.autograder_utils.files import SUBMISSION_BASE


TAB = " "*4

@contextmanager
def std_streams_suppressed():
    """
    Context manager to temporarily suppress stdout and stdin. Useful for loading
    submissions that may contain print() and input() invocations.
    """
    old_stdin = sys.stdin
    old_stdout = sys.stdout

    try:
        sys.stdout = StringIO()
        sys.stdin = StringIO()
        yield
    finally:
        sys.stdout = old_stdout
        sys.stdin = old_stdin

class CS1Submission():
    """
    Note: submissions will run in /autograder/submission dir in the autograder
    """
    @staticmethod
    def _load_if_exists(path):
        """
        If the file at the given path exists, read it and return its contents.
        Otherwise, returns None
        """
        if os.path.exists(path):
            with open(path, 'r') as f:
                return f.read()
        return None

    @staticmethod
    def _get_ast(filename: str) -> ast.Module:
        """Returns the AST of the file"""
        with open(filename, "r") as f:
            return ast.parse(f.read())

    def __init__(self, module_name: str, test_files=[]):
        # File names, path names
        self.problem_name = module_name
        self.filename = f"{module_name}.py"
        self.base = os.getenv("AUTOGRADER_SUBMISSION_PATH", SUBMISSION_BASE)
        self.path = os.path.join(self.base, self.filename)

        # References to submission and contents
        self.submission = self._load_if_exists(self.path)
        self.file_found = self.submission is not None
        self.tree = self._get_ast(self.path) if self.file_found else None
        self.functions = [node.name for node in ast.walk(self.tree) if isinstance(node, ast.FunctionDef)] if self.tree else []

        if test_files:
            for file in test_files:
                shutil.copy(file, self.base)

        self.files_dir = Path.cwd().parent / "source" / "tests" / self.problem_name

        load_dotenv('/autograder/.env')  # Load environment variables from .env file

        # Load OpenAI-related grading files, if they exist
        self.openai_client = None
        self.prompt = None
        prompt_template, rubric, problem = [
            self._load_if_exists(self.files_dir / file)
            for file in ['prompt_template.txt', 'rubric.txt', 'problem.md']
        ]
        
        # NOTE: This will fail if any of the files are missing of if the prompt template has different variables
        if all([prompt_template, rubric, problem]):
            prompt_template = cast(str, prompt_template)
            self.prompt = prompt_template.format(
                problem=problem, submission=self.submission, rubric=rubric)
            self.openai_client = OpenAI()
            
    def strip_input_prompt(self, stdout: str) -> str:
        """
        Finds the string prompt given to an input() call and removes it from the stdout.
        Assumes there is only ONE call to input
        """
        prompt = ""
        for node in ast.walk(self.tree):
            if (
                isinstance(node, ast.Call)
                and hasattr(node.func, "id")
                and node.func.id == "input"
                and hasattr(node, "args")
            ):
                if node.args and hasattr(node.args[0], "s"):
                    prompt = node.args[0].s

        return stdout.replace(prompt, "")

    def get_gpt_response(self, text):
        if not os.getenv("OPENAI_API_KEY"):
            raise Exception("OPENAI_API_KEY not set in /autograder/.env file") # NOTE: this is loaded in __init__

        try:
            completion = self.openai_client.chat.completions.create(
                model="gpt-5-mini",
                messages=[
                    {"role": "system", "content": text}
                ],
                # temperature=0 # gpt-5 doesn't support temperature
            )
        except Exception as e:
            print(f"Error getting GPT response: {e}")
            return None

        try:
            return completion.choices[0].message.content
        except Exception as e:
            print(f"Error parsing GPT response content: {e}")
            return None

    def has_function(self, function_name: str):
        return function_name in self.functions

    def get_function(self, function_name: str):
        """
        Returns a reference to the named function from the submission
        """
        with std_streams_suppressed():
            submission = import_module(self.filename)
            return getattr(submission, function_name)
        raise ValueError(f"Function {function_name} not found in submission")

    def function_param_count(self, function_name: str):
        """
        Returns the number of parameters the function takes
        """
        if function_name in self.functions:
            fn = self.get_function(function_name)
            return len(inspect.signature(fn).parameters)
        return None

    def get_io(self, user_input=None, argv=[]):
        """
        Gets program stdout and stderr and converts to utf-8.
        """
        # Prep the args for subprocess
        kwargs = {
            "args": ["python3", self.path] + argv,
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "universal_newlines": True
        }
        process = subprocess.Popen(**kwargs)

        # Get the outputs & convert to utf-8
        stdout, stderr = process.communicate(input=user_input)
        return stdout, stderr

    def get_function_io(self, function_name: str, args=None, stdin=None) -> tuple[str, str]:
        """
        Calls a function taking any number of parameters and returns any stdout and stderr it produces.

        Parameters:
        function_name (str): The name of the function to call.
        args (list, optional): A list of arguments to pass to the function. Defaults to None.
        stdin (list, optional): A list of strings to simulate user input. Each string represents a line of input. Defaults to None.

        Returns:
        tuple[str, str]: A tuple containing the captured stdout and stderr as strings.
        """

        # Append the base path to sys.path
        sys.path.append(self.base)

        try:
            # Import the module and function
            submission = import_module(self.problem_name)
            fn = getattr(submission, function_name)

        except Exception as e:
            print(f"Error during import or attribute retrieval: {e}")
            raise

        # Reassign stdout and stderr temporarily
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        old_stdin = sys.stdin
        stdout_capturer = StringIO()
        stderr_capturer = StringIO()

        if stdin:
            stdin_str = "\n".join(stdin) + "\n"
            sys.stdin = StringIO(stdin_str)

        sys.stdout = stdout_capturer
        sys.stderr = stderr_capturer
        

        # Call the function with or without arguments
        try:
            if args:
                fn(*args)
            else:
                fn()

        except Exception as e:
            # Log the error and restore stdout and stderr
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            sys.stdin = old_stdin
            print(f"Error occurred: {e}")
            raise

        finally:
            # Ensure stdout and stderr are restored even if an error occurs
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            sys.stdin = old_stdin

        return stdout_capturer.getvalue(), stderr_capturer.getvalue()

    def function_uses(self, function_name: str, check_fn) -> bool:
        """
        Returns True if function_name uses target in its source code
        """
        source = inspect.getsource(self.get_function(function_name))
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if check_fn(node):
                return True
        return False
    
    def has_hardcoded_print(self, regex) -> str:
        """
        Traverses the AST collecting all print nodes. Then it checks the args of each
        print node to see if it matches the regex.
        """
        # Get list of all print statement args
        print_node_args = (
            node.args
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Call)
            and hasattr(node.func, "id")
            and node.func.id == "print"
        )
        args = (arg for args in print_node_args for arg in args)

        # See if any arg matches the regex
        for arg in args:
            if isinstance(arg, ast.Constant) and regex.match(arg.value.lower()) is not None:
                return arg.value
        return None

    def prettify(self, s: str) -> str:
        return textwrap.fill(s, width=110, subsequent_indent=' '*14)


def set_deliverable_docstring(cls):
    """
    Decorator to set the docstring of the test_deliverables method. 
    
    The test_deliverables method is visible to students, showing them if they named their file
    and defined their functions correctly. Its docstring is what the students see in Gradescope
    as the test's name and description.
    """
    if cls.SUBMISSION_NAME:
        docstring = f"{cls.SUBMISSION_NAME}.py: testing that the required filename exists and required functions are defined with correct number of parameters."
        cls.test_deliverables.__doc__ = docstring
    return cls

@set_deliverable_docstring
class CS1TestCase(unittest.TestCase):
    """
    Subclasses TestCase with CS1 customizations. Currently, sets longMessage
    to False so we get more compact messages when tests fail. No other overrides

    Note: the test case instance runs in the same directory as run_tests.py
    """

    longMessage = False

    # Name of submission file without .py extension. Override in subclass
    SUBMISSION_NAME = None 
    
    # Override in subclass with dict {"fn_name": param_count, ...}
    REQUIRED_FUNCTIONS = None 

    # Optional list of test files to copy into submission dir
    TEST_FILES = []

    def __init__(self, methodName="runTest"):
        super().__init__(methodName)

    def __init_subclass__(cls, *args, **kwargs):
        """
        NOTE:  the unittest.TestLoader will try to instantiate this class under nearly all circumstances. But
        we don't want this class instantiated: we only to construct its subclasses, the test files. We want every
        subclass to have a test_deliverables method that produces student-readable output in Gradescope, so we'd
        want them to inherit this from the parent class. However, the test_deliverables method needs to know the
        SUBMISSION_NAME and REQUIRED_FUNCTIONS of the subclass, which are not known until the subclass gets constructed.

        The simplest solution I found was to use __init_subclass__ to add the SUBMISSION_NAME-dependent objects
        (the CS1Submission instance and the test_deliverables method). This way, no `test_` method exists
        on this class and constructing it does not affect the test suite that will run; subclasses will inherit
        the test_deliverables method which will use each subclass's SUBMISSION_NAME and REQUIRED_FUNCTIONS as intended.
        2025-09-26 BB
        """
        super().__init_subclass__(*args, **kwargs)

        if not cls.SUBMISSION_NAME:
            raise ValueError("SUBMISSION_NAME must be set in subclass of CS1TestCase")

        # Students often put unnecessary input() calls or remove the main() guard, so we suppress stdin/stdout while loading
        with std_streams_suppressed():
            cls.sub = CS1Submission(cls.SUBMISSION_NAME, test_files=cls.TEST_FILES)

        @weight(0)
        @visibility("visible")
        def test_deliverables(self):
            self.assertTrue(self.sub.file_found, f"`{self.SUBMISSION_NAME}.py` not found in submission")
            error_message = ""
            for fn, param_count in self.REQUIRED_FUNCTIONS.items():
                if not fn in self.sub.functions:
                    error_message += f"`{fn}()` not found in submission\n"
                    continue

                if not self.sub.function_param_count(fn) == param_count:
                    error_message += f"`{fn}()` should have {param_count} parameter(s), but was defined with {self.sub.function_param_count(fn)} parameter(s)\n"

            if error_message:
                # self.assertTrue(False, error_message)
                raise self.failureException(error_message)
            else:
                print("All checks passed!")
                self.assertTrue(True)
        test_deliverables.__doc__ = f"{cls.SUBMISSION_NAME}.py submission: Test that the required filename exists and required functions are defined with correct number of parameters."
        cls.test_deliverables = test_deliverables