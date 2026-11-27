"""What the scope skill and the whetstone-plan workflow say: the forms the skill takes, how it starts the driver,
what it ends with, and how both run commands."""
import re
import unittest
from pathlib import Path

from paths import COMMAND, REPO, WORKFLOW

import premise_report
import yaml  # Spec Kit's own dependency

SCRIPT_DIR = ".specify/extensions/whetstone-plan/scripts/"


def squashed(path: Path) -> str:
    return re.sub(r"\s+", " ", path.read_text())


def steps(nodes):
    """Every step of the workflow, nested ones included."""
    for node in nodes:
        yield node
        for key in ("then", "else"):
            yield from steps(node.get(key) or [])


class CommandSubstitution(unittest.TestCase):
    """A `$(...)` inside another command's arguments does not stop the shell when it fails: the command runs on an
    empty value (`gh --repo ""` picks another remote's repo). A value is read on its own, as `name=$(...)`, before
    the command that uses it."""
    READ_ON_ITS_OWN = re.compile(r"^\s*\w+=\$\(")

    def test_no_command_the_skill_or_the_workflow_give_reads_a_value_inside_its_arguments(self):
        commands = [("scope.md", c) for c in re.findall(r"`([^`]+)`", COMMAND.read_text())]
        commands += [("whetstone-plan.yml", line) for line in WORKFLOW.read_text().splitlines()]
        for where, command in commands:
            if "$(" not in command:
                continue
            with self.subTest(where=where, command=command):
                self.assertTrue(self.READ_ON_ITS_OWN.match(command) and command.count("$(") == 1)


class Scripts(unittest.TestCase):
    """Every script the workflow and the skill run is the extension's, and runs isolated, writing no compiled
    Python: a Whetstone review refuses compiled Python under .specify/."""

    def test_every_python_call_of_the_workflow_runs_an_extension_script_isolated(self):
        calls = re.findall(r"python3[^\n]*", WORKFLOW.read_text())
        self.assertTrue(calls)
        for call in calls:
            with self.subTest(call=call):
                self.assertRegex(call, r"^python3 -I -B \"?" + re.escape(SCRIPT_DIR) + r"\w+\.py")
                script = re.search(re.escape(SCRIPT_DIR) + r"(\w+\.py)", call)[1]
                self.assertTrue((REPO / "extensions" / "whetstone-plan" / "scripts" / script).is_file(), script)

    def test_the_skill_runs_its_scripts_isolated_from_the_paths_it_names(self):
        text = squashed(COMMAND)
        for name, script in (("DRIVE", "drive.py"), ("PREMISE", "premise_report.py")):
            with self.subTest(name=name):
                self.assertRegex(text, rf"`{name}` is `{re.escape(SCRIPT_DIR + script)}`")
                self.assertTrue((REPO / "extensions" / "whetstone-plan" / "scripts" / script).is_file())
        self.assertIn("run each as `python3 -I -B <script> ...`", text)
        self.assertNotRegex(text, r"`python3 (DRIVE|PREMISE)")

    def test_the_premise_gate_offers_exactly_the_three_outcomes_the_report_is_checked_against(self):
        gate = next(s for s in steps(yaml.safe_load(WORKFLOW.read_text())["steps"]) if s["id"] == "premise")
        self.assertEqual(tuple(gate["options"]), premise_report.OUTCOMES)

    def test_no_step_reaches_github_or_runs_node(self):
        runs = [s["run"] for s in steps(yaml.safe_load(WORKFLOW.read_text())["steps"]) if "run" in s]
        self.assertTrue(runs)
        for run in runs:
            with self.subTest(run=run):
                self.assertNotRegex(run, r"(^|[\s;|&(])(gh|node|curl|wget)\s|git\s+(push|commit)")


class ScopeSkill(unittest.TestCase):
    """What /speckit-whetstone-plan-scope takes, how it starts the driver, and what it ends with."""
    FORMS = ("#<issue>", "rescope <spec folder> #<issue>")
    ORIGIN = 'repo=$(git remote get-url origin) && gh issue view <ISSUE> --repo "$repo" '

    def test_takes_its_two_forms_and_refuses_anything_else_naming_them(self):
        text = COMMAND.read_text()
        for form in self.FORMS:
            with self.subTest(form=form):
                self.assertIn(f"- **`{form}`**", text)
        said = [s for s in re.split(r"(?<=\.)\s+", squashed(COMMAND)) if s.startswith("Anything else")]
        self.assertTrue([s for s in said if "the two forms" in s and "stop" in s], said)

    def test_its_description_names_the_workflow(self):
        front = yaml.safe_load(COMMAND.read_text().split("---\n")[1])
        self.assertIn("whetstone-plan", front["description"])

    def test_starts_the_driver_with_the_kind_of_run_the_spec_file_the_issue_and_the_folder(self):
        """Every run takes its folder; the subcommand, not whether a folder was given, says which kind it is."""
        self.assertIn("`python3 -I -B DRIVE start <SPEC_FILE> <ISSUE> <SPEC_DIR>` on a new scope, "
                      "`python3 -I -B DRIVE rescope <SPEC_FILE> <ISSUE> <SPEC_DIR>` on a rescope.", squashed(COMMAND))

    def new_scope(self):
        found = re.search(r"^- \*\*`#<issue>.*?(?=^- \*\*|^$)", COMMAND.read_text(), re.M | re.S).group(0)
        return re.sub(r"\s+", " ", found)

    def rescope(self):
        found = re.search(r"^- \*\*`rescope .*?(?=^- \*\*|^$)", COMMAND.read_text(), re.M | re.S).group(0)
        return re.sub(r"\s+", " ", found)

    def test_a_new_scope_picks_its_folder_once_from_one_to_four_words_of_the_issue_title(self):
        new_scope = self.new_scope()
        self.assertIn("`SPEC_DIR` is `specs/<ISSUE>-<short name>`, picked once, here", new_scope)
        self.assertIn("`<short name>` is 1 to 4 words of the issue title, lowercased, each a run of `[a-z0-9]`, "
                      "joined by single hyphens", new_scope)
        self.assertLess(new_scope.index("gh issue view"), new_scope.index("`<short name>` is 1 to 4 words"))

    def test_a_title_with_no_word_stops_before_anything_is_written_saying_to_retitle_the_issue(self):
        self.assertIn("A title with no such word: stop before writing anything, and tell the person to retitle the "
                      "issue.", self.new_scope())

    def test_a_rescope_writes_the_issue_as_first_stated_then_the_open_decision(self):
        """The folder may hold the wrong scope: the issue is read again from GitHub, not taken from the folder."""
        rescope = self.rescope()
        self.assertIn("the issue is re-read as first stated: write it to `SPEC_FILE` with the same `gh issue view` "
                      "command, then append", rescope)
        self.assertLess(rescope.index("`gh issue view`"), rescope.index("`Open decision: …`"))

    def test_every_issue_view_names_the_repo_by_origins_url(self):
        """origin is read before gh runs: a failed read inside gh's arguments leaves `--repo ""`, and gh picks a repo
        from the other remotes."""
        calls = re.findall(r"`([^`]*gh issue view [^`]*)`", COMMAND.read_text())
        self.assertTrue(calls)
        for call in calls:
            with self.subTest(call=call):
                self.assertTrue(call.startswith(self.ORIGIN), call)

    def test_a_completed_run_ends_with_the_spec_folder_and_leaves_the_commit_to_the_person(self):
        text = squashed(COMMAND)
        self.assertIn("End with `Spec folder: <SPEC_DIR>`", text)
        self.assertIn("to review it and commit it themselves", text)
        self.assertIn("Whetstone writes the spec folder and nothing else: it commits nothing, pushes nothing, and "
                      "posts nothing on GitHub.", text)
        self.assertNotRegex(text, r"git (commit|push)")

    def test_a_completed_run_says_what_stands_in_the_way_of_the_next_review(self):
        """Spec Kit records the folder in .specify/feature.json, and a review refuses any file under .specify/ that
        HEAD does not hold."""
        self.assertIn("`.specify/feature.json`", squashed(COMMAND).split("**Done.**", 1)[1])

    def test_refuses_a_harness_and_a_whetstone_agent(self):
        first = squashed(COMMAND).split("## Stop first if", 1)[1].split("## Paths", 1)[0]
        self.assertIn("`$TMPDIR` starts with `/tmp/whet.`", first)
        self.assertIn("a clone at `repo/`", first)

    def test_a_preflight_stop_is_the_persons_to_clear_and_resumes(self):
        stops = re.sub(r"\s+", " ", COMMAND.read_text().split("## Stops", 1)[1])
        self.assertIn("- `step: preflight`, with `stderr` lines that each name a Next step: show them to the person. "
                      "The person takes each step, not you; resume only once they say it is done.", stops)

    def test_no_spec_needed_says_the_folder_was_written_and_to_commit_it(self):
        said = [s for s in re.split(r"(?<=\.)\s+", squashed(COMMAND)) if s.startswith("After `no spec needed`")]
        self.assertTrue([s for s in said if "the workflow has written `SPEC_DIR` with a spec.md that says no spec is "
                         "needed" in s and "tell the person to commit it" in s], said)

    def test_a_rescope_of_a_no_spec_folder_is_expected_to_pause_at_the_premise(self):
        self.assertIn("on a rescope of a spec, `paused` at `grill`, and the next step is 4; on a rescope of a folder "
                      "whose spec.md says no spec is needed, `paused` at `premise`.", squashed(COMMAND))

    def test_names_the_premise_form_the_report_its_recommendation_and_pick_and_the_resume_in_that_order(self):
        text = squashed(COMMAND)
        order = ["PREMISE form", ".specify/workflows/runs/<run_id>/premise-report.md",
                 f"`{premise_report.RECOMMENDATION}:`", f"`{premise_report.PICK}:`", 'premise_verdict=<pick>"',
                 "/speckit-grill-me"]
        positions = [text.find(step) for step in order]
        self.assertNotIn(-1, positions, list(zip(order, positions)))
        self.assertEqual(positions, sorted(positions))
        for outcome in premise_report.OUTCOMES:
            with self.subTest(outcome=outcome):
                self.assertIn(f"`{outcome}`", text)
        self.assertIn("Never ask for approve or reject at this step.", text)
        self.assertIn("Ask the person only what the issue and the code cannot answer.", text)

    def test_a_no_spec_folder_that_cannot_be_written_is_a_stop_that_resumes(self):
        stops = re.sub(r"\s+", " ", COMMAND.read_text().split("## Stops", 1)[1])
        self.assertIn("- `step: write-no-spec`, with a `stderr` line that names a Next step: show the person the "
                      "message. When it names a path to clear or make writable, the person does that, not you; resume "
                      "only once they say it is done. When it names `premise_report.py check`, complete the report as "
                      "it says.", stops)

    def test_verdicts_are_the_persons(self):
        self.assertIn("Never pass `approve`, or a premise pick, without the person saying so in this session.",
                      squashed(COMMAND))


if __name__ == "__main__":
    unittest.main()
