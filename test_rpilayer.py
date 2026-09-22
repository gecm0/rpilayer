from rpilayer import ARTIFACT, checkboxes, next_step, open_design_questions, current_phase, render, steps

assert ARTIFACT.match("01-research-questions-auth.md")[2] == "research-questions"
assert ARTIFACT.match("02-research-auth.md")[2] == "research"
assert ARTIFACT.match("ticket.md") is None

assert next_step(None) == "create-research-questions"
assert next_step("research-questions") == "create-research"
assert next_step("design-discussion", open_questions=2) == "iterate-design-discussion"
assert next_step("design-discussion", open_questions=0) == "create-structure-outline"
assert next_step("structure-outline", unchecked=3) == "implement-outline"
assert next_step("plan", unchecked=1) == "implement-plan"
assert next_step("plan", unchecked=0, checked=4) == "describe-pr"

doc = "### Design Questions\n\n#### A\nx\n#### B\n\n### Resolved Design Questions\n\n#### C\n"
assert open_design_questions(doc) == 2
assert open_design_questions("### Design Questions\n\n### Resolved Design Questions\n#### C\n") == 0
assert checkboxes("- [ ] a\n  - [x] b\n- [X] c\n") == (1, 2)
outline = "- [x] Phase 1: a\n- [x] Phase 2: b\n## Phase 2\n- [ ] manual device check\n"
assert checkboxes(outline) == (0, 2)
unchecked, checked = checkboxes(outline)
assert next_step("structure-outline", unchecked=unchecked, checked=checked) == "describe-pr"

page = render("<title>{{TITLE}}</title>{ css }{{CONTENT}}<i>{{SOURCE}}</i>", "A & B", "<p>{x}</p>", "01-x.md")
assert page == "<title>A &amp; B</title>{ css }<p>{x}</p><i>01-x.md</i>"


def marks(result):
    return " ".join(f"{s['label']}:{s['status']}" + (f"({s['detail']})" if "detail" in s else "") for s in result)


assert marks(steps([], "create-research-questions")) == (
    "questions:current research:todo design:todo outline:todo implement:todo pr:todo")
assert marks(steps(["research-questions", "research", "design-discussion"], "iterate-design-discussion", 2)) == (
    "questions:done research:done design:current(2 open) outline:todo implement:todo pr:todo")
# Went straight from research to the outline: design was skipped, not done.
assert marks(steps(["research-questions", "research", "structure-outline"], "implement-outline",
                   unchecked=3, checked=2)) == (
    "questions:done research:done design:skipped outline:done implement:current(phase 3/5) pr:todo")
# Product track, with a research document added along the way and a plan.
assert marks(steps(["prd", "research", "tdd", "plan"], "describe-pr", checked=4)) == (
    "prd:done research:done tdd:done plan:done implement:done(4/4) pr:current")
assert current_phase("- [x] Phase 1: a\n- [ ] Phase 2: Add pagination \n- [ ] Phase 3: c\n") == "Phase 2: Add pagination"
assert current_phase("- [x] Phase 1: a\n") is None
implementing = steps(["structure-outline"], "implement-outline", unchecked=2, checked=1, phase="Phase 2: b")
assert [s.get("doing") for s in implementing if s["name"] == "implement"] == ["Phase 2: b"]
print("ok")
