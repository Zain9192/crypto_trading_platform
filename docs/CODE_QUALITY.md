# Code Quality Tooling

The repository uses automated tests plus SonarQube/SonarQube Cloud integration and Checkstyle support.

## SonarQube / SonarQube Cloud

Configuration is stored in `sonar-project.properties` and CI integration is in `.github/workflows/sonar.yml`.

The workflow is safe before a Sonar project is connected: it reports a skipped analysis instead of failing when Sonar credentials are not configured.

Configure these GitHub repository settings to activate analysis:

- Secret `SONAR_TOKEN` — required.
- Variable `SONAR_HOST_URL` — set this for SonarQube Server. It is not required for SonarQube Cloud.
- Variable `SONAR_ORGANIZATION` — set this for SonarQube Cloud.
- Variable `SONAR_PROJECT_KEY` — optional override. The default is `crypto_trading_platform`.

Once configured, pushes and pull requests run the official SonarQube scan action followed by the Sonar quality-gate check. A failed configured quality gate fails the Sonar workflow.

The scan currently covers:

- `backend/app` — Python application code.
- `frontend/src` — TypeScript/React application code.
- `backend/tests` — backend tests.

Generated/build/dependency directories are excluded.

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

Do not treat Checkstyle as a Python or TypeScript linter. Sonar analyzes the project's current Python and TypeScript source directly. If dedicated language-specific lint gates are added later, use Python and TypeScript-native tooling rather than forcing Java Checkstyle rules onto those languages.
