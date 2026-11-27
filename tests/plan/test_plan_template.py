"""The settled-design preset teaches the formats whetstone-plan's checks read; these pin each format to its check."""
import json
import re
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from paths import PRESET

import premise_report
import rootcause
import settled_design


def setUpModule():
    """A new Claude Code Spec Kit project with the preset installed from this repository's source."""
    global PROJECT
    PROJECT = tempfile.TemporaryDirectory()
    subprocess.run(["specify", "init", "--here", "--integration", "claude", "--script", "sh", "--ignore-agent-tools",
                    "--force"], cwd=PROJECT.name, check=True, capture_output=True, text=True)
    subprocess.run(["specify", "preset", "add", "--dev", str(PRESET)], cwd=PROJECT.name, check=True,
                   capture_output=True, text=True)


def tearDownModule():
    PROJECT.cleanup()


def composed_plan() -> str:
    """plan.md as speckit.plan's setup script writes it."""
    root = Path(PROJECT.name)
    feature = root / "specs" / "7-demo"
    feature.mkdir(parents=True, exist_ok=True)
    (feature / "spec.md").write_text("# Spec\n")
    (root / ".specify" / "feature.json").write_text(json.dumps({"feature_directory": str(feature)}))
    subprocess.run(["bash", ".specify/scripts/bash/setup-plan.sh", "--json"], cwd=root, check=True,
                   capture_output=True, text=True)
    return (feature / "plan.md").read_text()


def composed_spec_template() -> str:
    """The spec template as speckit.specify resolves it."""
    return subprocess.run(["bash", ".specify/scripts/bash/resolve-template.sh", "spec-template"], cwd=PROJECT.name,
                          check=True, capture_output=True, text=True).stdout


def installed_skill_carries(command: str) -> bool:
    addition = (PRESET / "commands" / f"{command}.md").read_text().split("---\n", 2)[2].strip()
    skill = Path(PROJECT.name) / ".claude" / "skills" / command.replace(".", "-") / "SKILL.md"
    return skill.read_text().rstrip().endswith(addition)


class SpecTemplate(unittest.TestCase):
    def test_the_composed_spec_template_has_the_premise_and_root_cause_sections(self):
        headings = [line for line in composed_spec_template().splitlines() if line.startswith("## ")]
        self.assertEqual(headings[-2:], ["## Why this is worth doing", rootcause.HEADING])
        self.assertIn("## Requirements *(mandatory)*", headings)

    def test_the_template_asks_for_the_reports_questions_under_its_headings(self):
        asked = [line[4:] for line in composed_spec_template().splitlines() if line.startswith("### ")
                 and line[4:] in premise_report.QUESTIONS]
        self.assertEqual(asked, list(premise_report.QUESTIONS))

    def test_the_template_as_shipped_fails_both_checks_and_passes_them_once_filled(self):
        template = composed_spec_template()
        self.assertEqual(len(premise_report.spec_problems(template)), 2 * len(premise_report.QUESTIONS))
        self.assertEqual(len(rootcause.problems(template, None)), 1)
        filled = re.sub(r"^(Answer|Source|Observed): \[.*\]$",
                        lambda line: f"{line[1]}: {'code: scripts/gate.py' if line[1] == 'Source' else 'observed: a KeyError'}",
                        template, flags=re.MULTILINE)
        self.assertEqual(premise_report.spec_problems(filled), [])
        self.assertEqual(rootcause.problems(filled, None), [])

    def test_the_template_spells_the_root_cause_sentences_as_their_readers_read_them(self):
        """rootcause.py accepts only these spellings, so a template teaching another wording would fail every spec
        written from it."""
        for sentence in (rootcause.NOT_A_DEFECT, rootcause.HYPOTHESIS):
            with self.subTest(sentence=sentence):
                self.assertIn(f"`{sentence}`", composed_spec_template())

    def test_the_installed_specify_command_says_where_the_premise_answers_come_from(self):
        self.assertTrue(installed_skill_carries("speckit.specify"), "speckit-specify lacks the settled-design preset")


class PlanTemplate(unittest.TestCase):
    def test_the_composed_plan_templates_example_passes_the_check(self):
        plan = composed_plan()
        example = re.search(r"^( {4}## R1:.*?)^-->", plan, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(example, "the composed plan template has no indented research.md example")
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "plan.md").write_text(plan)
            (Path(tmp) / "research.md").write_text(textwrap.dedent(example[1]))
            self.assertEqual(settled_design.problems(Path(tmp)), [])

    def test_the_installed_plan_command_carries_the_presets_research_format(self):
        self.assertTrue(installed_skill_carries("speckit.plan"), "speckit-plan SKILL.md lacks the settled-design preset")


if __name__ == "__main__":
    unittest.main()
