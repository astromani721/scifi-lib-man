from __future__ import annotations

from pathlib import Path


try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - fallback for older Python
    import tomli as tomllib


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject = root / "pyproject.toml"
    requirements = root / "requirements.txt"

    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    deps = data.get("project", {}).get("dependencies", [])
    dev_deps = data.get("project", {}).get("optional-dependencies", {}).get("dev", [])

    requirements.write_text("\n".join(deps) + "\n", encoding="utf-8")

    requirements_dev = root / "requirements-dev.txt"
    requirements_dev.write_text("\n".join(dev_deps) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
