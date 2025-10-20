import nox

PYTHON = "3.11"

@nox.session(python=PYTHON)
def lint(session: nox.Session) -> None:
    session.install("ruff>=0.6.0", "black>=24.0.0")
    session.run("ruff", "check", ".")
    session.run("black", "--check", "src", "noxfile.py")


@nox.session(python=PYTHON)
def typecheck(session: nox.Session) -> None:
    session.install("mypy>=1.10.0", "types-PyYAML>=6.0.12.20240808")
    session.install("-e", ".")
    session.run("mypy", "src")


@nox.session(python=PYTHON)
def format(session: nox.Session) -> None:
    session.install("ruff>=0.6.0", "black>=24.0.0")
    session.run("ruff", "check", "--fix", ".")
    session.run("black", "src", "noxfile.py")
