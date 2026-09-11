# Code Quality Tooling

The repository uses GitHub Actions backend/frontend tests and frontend production builds, plus Checkstyle support for any future Java code.

## SonarQube — deferred

SonarQube was removed at the project owner's request on 2026-09-10. No scan workflow or Sonar project configuration is currently active. It can be added in a later feature branch. No repository secrets or account settings were changed.

## Checkstyle

Checkstyle is a Java-specific static-analysis/style tool. The current project backend is Python and the frontend is TypeScript, so there are currently no Java files for Checkstyle to inspect.

Checkstyle support is nevertheless configured as requested so it will activate automatically if Java source code is introduced later:

- Rules: `config/checkstyle/checkstyle.xml`
- Runner: `scripts/run-checkstyle.sh`
- CI job: `Checkstyle` in `.github/workflows/ci.yml`
- Pinned Checkstyle version: `14.1.0`

With the current codebase, the Checkstyle job succeeds with an explicit `No Java source files found` message rather than pretending to analyze Python or TypeScript.

To run it locally:

```bash
./scripts/run-checkstyle.sh
```

If Java files exist, Java 21+ and `curl` are required. The script downloads the pinned Checkstyle all-in-one JAR into a temporary cache and runs the repository rules against every Java source file.

## Important distinction

Do not treat Checkstyle as a Python or TypeScript linter. If dedicated language-specific lint gates are added later, use Python and TypeScript-native tooling rather than forcing Java Checkstyle rules onto those languages.
