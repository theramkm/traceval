from pathlib import Path

import jinja2


def emit_pytest_suite(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    templates_dir = Path(__file__).parent / "templates"
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(templates_dir)),
        autoescape=False,
    )

    conftest_tmpl = env.get_template("conftest.py.jinja")
    conftest_content = conftest_tmpl.render()
    (output_dir / "conftest.py").write_text(conftest_content, encoding="utf-8")

    test_gen_tmpl = env.get_template("test_generated.py.jinja")
    test_gen_content = test_gen_tmpl.render()
    (output_dir / "test_generated.py").write_text(test_gen_content, encoding="utf-8")
