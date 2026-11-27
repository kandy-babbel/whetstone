import sys
from pathlib import Path

# The tests sit outside the extension, so they cannot find its scripts beside themselves.
REPO = Path(__file__).resolve().parents[2]
EXTENSION = REPO / "extensions" / "whetstone-plan"
SCRIPTS = EXTENSION / "scripts"
COMMAND = EXTENSION / "commands" / "scope.md"
WORKFLOW = REPO / "workflows" / "whetstone-plan.yml"
PRESET = REPO / "presets" / "whetstone-settled-design"
# How the workflow and the skill run each script: isolated, so the script's own folder is not on the path, and
# writing no compiled Python, which a Whetstone review refuses under .specify/.
PY = (sys.executable, "-I", "-B")
sys.path.insert(0, str(SCRIPTS))
sys.dont_write_bytecode = True
